# app/main.py
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from app.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.tasks import tasks_router, public_router
from app.api.routes.telegram import router as telegram_router

__all__ = ["app"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    An async context manager for the lifespan of the application.

    Args:
        app (FastAPI): The FastAPI application.
    """
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

app.include_router(health_router,   prefix="/health",   tags=["health"])
app.include_router(telegram_router)
app.include_router(tasks_router)
app.include_router(public_router)

_request_logger = logging.getLogger("request")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    A middleware for logging HTTP requests.

    Args:
        request (Request): The incoming request.
        call_next: The next middleware in the chain.

    Returns:
        The response from the next middleware.
    """
    start = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000.0
        _request_logger.exception(
            "request method=%s path=%s status=500 duration_ms=%.2f request_id=%s",
            request.method,
            request.url.path,
            duration_ms,
            request_id,
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000.0
    response.headers["X-Request-ID"] = request_id
    _request_logger.info(
        "request method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response
