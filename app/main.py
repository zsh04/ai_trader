# app/main.py (health++ / notify wiring)
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, Query, Depends, Header
from sqlalchemy import text

from app.config import settings
from app.adapters.db.postgres import make_engine as pg_engine, make_session_factory
from app.scanners.watchlist_builder import build_watchlist
from app.adapters.storage.blob import *  # if you rely on these elsewhere
from pydantic import BaseModel

from app.utils.env import TELEGRAM_DEFAULT_CHAT_ID
from app.wiring.telegram import get_telegram, TelegramDep
from app.adapters.notifiers.telegram import send_watchlist

app = FastAPI(title="AI Trader", version="0.1.0")


@app.on_event("startup")
def _startup():
    # Warm the singleton so errors surface early
    _ = get_telegram()


@app.post("/notify/test")
def notify_test(tg = Depends(TelegramDep)):
    chat = int(TELEGRAM_DEFAULT_CHAT_ID) if TELEGRAM_DEFAULT_CHAT_ID else None
    if not chat:
        return {"ok": False, "msg": "Set TELEGRAM_DEFAULT_CHAT_ID to test quickly."}
    ok = tg.smart_send(chat, "Hello from *AI Trader* — Markdown test ✅")
    return {"ok": ok}


@app.post("/telegram/webhook")
def telegram_webhook(
    tg = Depends(TelegramDep),
    x_telegram_secret: str | None = Header(None),
    payload: dict | None = None,
):
    if not tg.verify_webhook(x_telegram_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Basic allowlist (optional)
    chat_id = (((payload or {}).get("message") or {}).get("chat") or {}).get("id")
    if chat_id is None or not tg.is_allowed(int(chat_id)):
        raise HTTPException(status_code=403, detail="Unauthorized chat")

    # Echo or handle commands
    text_in = ((payload or {}).get("message") or {}).get("text") or ""
    if text_in.strip() == "/ping":
        tg.smart_send(int(chat_id), "pong")
    else:
        tg.smart_send(int(chat_id), f"Received: `{text_in}`")

    return {"ok": True}


# ------------------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------------------

def _check_blob() -> tuple[bool, str]:
    try:
        from azure.storage.blob import BlobServiceClient
        conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if conn:
            bsc = BlobServiceClient.from_connection_string(conn)
        else:
            bsc = BlobServiceClient(
                f"https://{settings.blob_account}.blob.core.windows.net",
                credential=settings.blob_key,
            )
        # lightweight call
        next(bsc.list_containers(), None)
        return True, "ok"
    except Exception as e:
        return False, str(e)


def _check_db() -> tuple[bool, str]:
    try:
        eng = pg_engine()
        with eng.begin() as cx:
            cx.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as e:
        return False, str(e)


@app.get("/health")
def health():
    blob_ok, blob_msg = _check_blob()
    db_ok, db_msg = _check_db()
    status = "ok" if (blob_ok and db_ok) else "degraded"
    return {
        "status": status,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "tz": settings.tz,
        "blob": {"ok": blob_ok, "msg": (blob_msg or "")[:160]},
        "db": {"ok": db_ok, "msg": (db_msg or "")[:160]},
    }


# ------------------------------------------------------------------------------
# Watchlist Task
# ------------------------------------------------------------------------------
class ScanRequest(BaseModel):
    symbols: Optional[List[str]] = None
    debug: bool = False


@app.post("/tasks/watchlist")
def watchlist_task(
    symbols: Optional[List[str]] = Query(None),
    include_filters: bool = Query(True),
    passthrough: bool = Query(False),
    include_ohlcv: bool = Query(True),
    debug: bool = Query(False),
    # NEW: Telegram notification controls
    notify: bool = Query(False, description="If true, send the built watchlist to Telegram"),
    chat_id: Optional[str] = Query(None, description="Override Telegram chat id"),
    title: Optional[str] = Query(None, description="Optional title for Telegram message header"),
):
    wl = build_watchlist(
        symbols=symbols,
        include_filters=include_filters,
        passthrough=passthrough,
        include_ohlcv=include_ohlcv,
    )

    # Optionally notify via Telegram
    if notify:
        try:
            session = wl.get("session", "regular") if isinstance(wl, dict) else "regular"
            items = wl.get("items", []) if isinstance(wl, dict) else []
            send_watchlist(session, items, chat_id=chat_id, title=(title or "AI Trader • Watchlist"))
        except Exception as e:
            # Best-effort: don't fail the API if Telegram is misconfigured
            # (use /notify/test to validate bot/chat config independently)
            print(f"[watchlist_task] Telegram send failed: {e}")

    return wl