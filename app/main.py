# app/main.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query
from sqlalchemy import text

from app import __version__
from app.adapters.db.postgres import make_engine as pg_engine
from app.adapters.notifiers.telegram import TelegramClient, send_watchlist
from app.api import get_api_router
from app.config import settings
from app.scanners.watchlist_builder import build_watchlist
from app.utils import env as ENV
from app.utils.env import TELEGRAM_DEFAULT_CHAT_ID
from app.wiring.telegram import TelegramDep, get_telegram
from app.wiring import telegram_router
from app.api.routes import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    yield


app = FastAPI(title="AI Trader", version=settings.VERSION, lifespan=lifespan)
app.include_router(telegram_router.router)
app.include_router(api_router)


# ------------------------------------------------------------------------------
# Lightweight bot sanity ping (kept in main, but no Annotated usage)
# ------------------------------------------------------------------------------
@app.post("/notify/test")
def notify_test(tg: TelegramClient = Depends(TelegramDep)) -> Dict[str, Any]:
    chat = int(TELEGRAM_DEFAULT_CHAT_ID) if TELEGRAM_DEFAULT_CHAT_ID else None
    if not chat:
        return {"ok": False, "msg": "Set TELEGRAM_DEFAULT_CHAT_ID to test quickly."}
    ok = tg.smart_send(chat, "Hello from *AI Trader* — Markdown test ✅")
    return {"ok": ok}


# NOTE: DO NOT define /telegram/webhook here.
# The webhook route lives in app.wiring.telegram_router and is already included.


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
        next(bsc.list_containers(), None)  # lightweight call
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
from pydantic import BaseModel  # keep local to avoid unused-import warnings


class ScanRequest(BaseModel):
    symbols: Optional[List[str]] = None
    debug: bool = False


@app.post("/tasks/watchlist")
def watchlist_task(
    symbols: Optional[List[str]] = Query(None),
    include_filters: bool = Query(True),
    passthrough: bool = Query(False),
    include_ohlcv: bool = Query(True),
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

    if notify:
        try:
            session = wl.get("session", "regular") if isinstance(wl, dict) else "regular"
            items = wl.get("items", []) if isinstance(wl, dict) else []
            send_watchlist(
                session,
                items,
                chat_id=chat_id,
                title=(title or "AI Trader • Watchlist"),
            )
        except Exception as e:
            # Best-effort: don't fail the API if Telegram is misconfigured
            print(f"[watchlist_task] Telegram send failed: {e}")

    return wl