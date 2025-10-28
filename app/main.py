# app/main.py
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.config import settings
from app.wiring import telegram_router
from app.wiring.telegram_router import TelegramDep, get_telegram

__all__ = ["app", "TelegramDep"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging

    logger = logging.getLogger(__name__)

    # Light env sanity (log missing critical settings but don't block boot)
    required = {
        "ALPACA_API_KEY": settings.alpaca_key,
        "ALPACA_API_SECRET": settings.alpaca_secret,
        "AZURE_STORAGE_ACCOUNT": settings.blob_account,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        logger.warning("Missing required env vars: %s", ",".join(missing))

    # Warm up Telegram client (best-effort)
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


# FastAPI application
app = FastAPI(title="AI Trader", version=settings.VERSION, lifespan=lifespan)

# Routers (define all endpoints in their own modules; keep main clean)
app.include_router(telegram_router.router)
app.include_router(api_router)
