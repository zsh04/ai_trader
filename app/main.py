# app/main.py
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings

# bring routers in explicitly
from app.api.routes.health import router as health_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.telegram import router as telegram_router

__all__ = ["app"]

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

    logger.info(
        "AI Trader %s port=%s tz=%s env=%s",
        settings.VERSION, settings.port, settings.tz, os.getenv("ENV", "local"),
    )
    yield

app = FastAPI(title="AI Trader", version=settings.VERSION, lifespan=lifespan)

# Give each router a non-empty prefix to avoid “Prefix and path cannot be both empty”
app.include_router(health_router,   prefix="/health",   tags=["health"])
app.include_router(tasks_router,    prefix="/tasks",    tags=["tasks"])
app.include_router(telegram_router, prefix="/telegram", tags=["telegram"])