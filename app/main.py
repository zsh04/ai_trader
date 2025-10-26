# app/main.py (health++ / notify wiring)
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, Header, HTTPException, Query, Request, FastAPI, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

# JSONResponse must come from starlette
from app import __version__
from app.adapters.db.postgres import make_engine as pg_engine
from app.adapters.notifiers.telegram import TelegramClient, send_watchlist
from app.api import get_api_router
from app.config import settings
from app.scanners.watchlist_builder import build_watchlist
from app.utils import env as ENV
from app.utils.env import TELEGRAM_DEFAULT_CHAT_ID, TELEGRAM_WEBHOOK_SECRET
from app.wiring.telegram import TelegramDep, get_telegram

app = FastAPI(title="AI Trader", version=settings.VERSION)
app.include_router(get_api_router())


@app.on_event("startup")
def _startup():
    import logging

    logger = logging.getLogger(__name__)
    required = {
        "ALPACA_API_KEY": settings.alpaca_key,
        "ALPACA_API_SECRET": settings.alpaca_secret,
        "AZURE_STORAGE_ACCOUNT": settings.blob_account,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        logger.warning("Missing required env vars: %s", ",".join(missing))

    try:
        _ = get_telegram()
    except Exception as exc:
        logger.warning("Telegram warm-up failed: %s", exc)

    logger.info(
        "AI Trader %s port=%s tz=%s env=%s",
        settings.VERSION,
        settings.port,
        settings.tz,
        os.getenv("ENV", "local"),
    )


@app.post("/notify/test")
def notify_test(tg: Annotated["TelegramClient", Depends(TelegramDep)]):
    chat = int(TELEGRAM_DEFAULT_CHAT_ID) if TELEGRAM_DEFAULT_CHAT_ID else None
    if not chat:
        return {"ok": False, "msg": "Set TELEGRAM_DEFAULT_CHAT_ID to test quickly."}
    ok = tg.smart_send(chat, "Hello from *AI Trader* — Markdown test ✅")
    return {"ok": ok}


@app.post("/telegram/webhook", response_model=None)
async def telegram_webhook(
    request: Request,
    tg: Annotated["TelegramClient", Depends(TelegramDep)],
    x_telegram_bot_api_secret_token: Optional[str] = Header(
        None, convert_underscores=False
    ),
    x_telegram_secret_token: Optional[str] = Header(None, convert_underscores=False),
):
    secret = x_telegram_bot_api_secret_token or x_telegram_secret_token
    expected_secret = TELEGRAM_WEBHOOK_SECRET
    if expected_secret and secret != expected_secret:
        raise HTTPException(status_code=401, detail="invalid secret")

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as err:
        raise HTTPException(status_code=400, detail="invalid JSON") from err

    msg = payload.get("message") or payload.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()

    if not chat_id:
        raise HTTPException(status_code=400, detail="missing chat id")

    if text.startswith("/ping"):
        tg.send_text(chat_id, "pong")
    else:
        tg.send_text(chat_id, "✅ webhook up")

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
        "version": __version__,
    }


# ------------------------------------------------------------------------------
# Watchlist Task
# ------------------------------------------------------------------------------
class ScanRequest(BaseModel):
    symbols: Optional[List[str]] = None
    debug: bool = False


@app.post("/tasks/watchlist")
def watchlist_task(
    symbols: Annotated[Optional[List[str]], Query(None)],
    include_filters: Annotated[bool, Query(True)],
    passthrough: Annotated[bool, Query(False)],
    include_ohlcv: bool = Query(True),
    debug: bool = Query(False),
    # NEW: Telegram notification controls
    notify: bool = Query(
        False, description="If true, send the built watchlist to Telegram"
    ),
    chat_id: Optional[str] = Query(None, description="Override Telegram chat id"),
    title: Optional[str] = Query(
        None, description="Optional title for Telegram message header"
    ),
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
            session = (
                wl.get("session", "regular") if isinstance(wl, dict) else "regular"
            )
            items = wl.get("items", []) if isinstance(wl, dict) else []
            send_watchlist(
                session,
                items,
                chat_id=chat_id,
                title=(title or "AI Trader • Watchlist"),
            )
        except Exception as e:
            # Best-effort: don't fail the API if Telegram is misconfigured
            # (use /notify/test to validate bot/chat config independently)
            print(f"[watchlist_task] Telegram send failed: {e}")

    return wl
