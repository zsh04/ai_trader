# app/main.py
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from loguru import logger

import app as app_package  # noqa: F401  # ensure package __init__ (Sentry) runs
from app.api.routes.health import router as health_router
from app.api.routes.tasks import public_router, tasks_router
from app.api.routes.telegram import router as telegram_router
from app.config import settings
from app.logging_utils import logging_context, setup_logging
from app.observability import configure_observability

__all__ = ["app"]


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    configure_observability()

    required = {
        "ALPACA_API_KEY": settings.alpaca_key,
        "ALPACA_API_SECRET": settings.alpaca_secret,
        "AZURE_STORAGE_ACCOUNT": settings.blob_account,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        logger.warning("Missing required env vars: {}", ",".join(missing))

    logger.info(
        "AI Trader {} port={} tz={} env={}",
        settings.VERSION,
        settings.port,
        settings.tz,
        os.getenv("ENV", "local"),
    )
    yield


app = FastAPI(title="AI Trader", version=settings.VERSION, lifespan=lifespan)

# Give each router a non-empty prefix to avoid “Prefix and path cannot be both empty”
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(telegram_router)
app.include_router(tasks_router)
app.include_router(public_router)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    request.state.request_id = request_id
    with logging_context(request_id=request_id):
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000.0
            logger.exception(
                "request method={} path={} status=500 duration_ms={:.2f}",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request method={} path={} status={} duration_ms={:.2f}",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
