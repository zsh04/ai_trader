# app/main.py
from __future__ import annotations
import sentry_sdk
import logging
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from app.config import settings

# bring routers in explicitly
from app.api.routes.health import router as health_router
from app.api.routes.tasks import tasks_router, public_router
from app.api.routes.telegram import router as telegram_router

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    environment=os.getenv("APP_ENVIRONMENT", "dev")
)


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
app.include_router(telegram_router)
app.include_router(tasks_router)
app.include_router(public_router)

_request_logger = logging.getLogger("request")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
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
