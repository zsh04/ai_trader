from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

try:
    from app import __version__ as APP_VERSION
except Exception:
    try:
        from app.utils import env as ENV

        APP_VERSION = getattr(ENV, "APP_VERSION", "0.1.0")
    except Exception:
        APP_VERSION = "0.1.0"

from app.adapters.db.postgres import ping
from app.domain.watchlist_service import get_watchlist_counters
from app.settings import get_database_settings

router = APIRouter(tags=["health"])


@router.get("")
async def health() -> Dict[str, Any]:
    """
    Legacy health endpoint.

    Returns:
        Dict[str, Any]: A dictionary with the health status.
    """
    return await health_live()


@router.get("/live")
async def health_live() -> Dict[str, Any]:
    """
    A lightweight liveness probe.

    Returns:
        Dict[str, Any]: A dictionary with the service status and version.
    """
    return {"ok": True, "service": "ai-trader", "version": APP_VERSION}


@router.get("/db")
async def health_db() -> Dict[str, Any]:
    """
    Database connectivity probe.

    Returns:
        Dict[str, Any]: A dictionary with the database status and latency.
    """
    t0 = time.perf_counter()
    ok = False
    try:
        ok = bool(ping(retries=1))
    except Exception:
        ok = False
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    return {"status": "ok" if ok else "degraded", "latency_ms": latency_ms}


@router.get("/ready")
async def health_ready() -> Dict[str, str]:
    """
    A lightweight readiness probe.

    Returns:
        Dict[str, str]: A dictionary with the readiness status and timestamp.
    """
    return {"status": "ok", "utc": datetime.now(timezone.utc).isoformat()}


@router.get("/market")
async def health_market():
    """
    Market data provider connectivity probe.

    Returns:
        Dict[str, Any]: A dictionary with the market data provider status.
    """
    import logging
    import os

    from app.adapters.market.alpaca_client import AlpacaPingError, ping_alpaca

    feed = os.getenv("ALPACA_DATA_FEED", "").lower() or "iex"
    try:
        ok, meta = await run_in_threadpool(
            lambda: ping_alpaca(feed=feed, timeout_sec=4.0)
        )
        return {"status": "ok" if ok else "degraded", "feed": feed, "meta": meta}
    except AlpacaPingError as e:
        logging.warning("market ping failed: %s", e)
        return {"status": "degraded", "feed": feed, "reason": str(e)}


@router.get("/version")
async def version() -> Dict[str, str]:
    """
    Exposes the application version.

    Returns:
        Dict[str, str]: A dictionary with the application version.
    """
    return {"version": APP_VERSION}


@router.get("/sentry-debug")
async def trigger_error():
    raise ZeroDivisionError("sentry debug route triggered")


def _mask(value: str | None) -> str:
    """
    Masks a string value.

    Args:
        value (str | None): The string to mask.

    Returns:
        str: The masked string.
    """
    if not value:
        return ""
    prefix = 2
    suffix = 4
    stripped = value.strip()
    if len(stripped) <= prefix + suffix:
        if len(stripped) <= 2:
            return stripped[:1] + "*" * max(len(stripped) - 1, 0)
        return stripped[:prefix] + "*" * (len(stripped) - prefix)
    return (
        stripped[:prefix] + "*" * (len(stripped) - prefix - suffix) + stripped[-suffix:]
    )


@router.get("/config")
async def health_config() -> Dict[str, Any]:
    """
    Exposes the application configuration.

    Returns:
        Dict[str, Any]: A dictionary with the application configuration.
    """
    env = os.getenv("ENV", "dev").lower()

    database_settings = get_database_settings()

    database_url = database_settings.primary_dsn or ""
    alpaca_key = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret = os.getenv("ALPACA_API_SECRET", "")
    alpaca_feed = os.getenv("ALPACA_FEED", "iex")
    watchlist_source = os.getenv("WATCHLIST_SOURCE", "")
    textlist_backends = os.getenv("TEXTLIST_BACKENDS", "")

    has_db = bool(database_url)
    has_alpaca = bool(alpaca_key and alpaca_secret)

    parsed = urlparse(database_url) if database_url else None
    db_host = parsed.hostname if parsed else ""
    db_name = parsed.path.lstrip("/") if parsed else ""
    masked_db = ""
    if db_host or db_name:
        masked_db = f"{_mask(db_host)}/{_mask(db_name)}".strip("/")

    config = {
        "database_url": masked_db or _mask(database_url),
        "alpaca_api_key": _mask(alpaca_key),
        "alpaca_feed": alpaca_feed,
        "watchlist_source": watchlist_source or "textlist",
        "textlist_backends": textlist_backends,
    }

    checks = {
        "has_db_url": has_db,
        "has_alpaca_keys": has_alpaca,
    }

    required_ok = has_db and has_alpaca
    status = "ok"
    if env == "prod" and not required_ok:
        status = "degraded"

    env_dump = {
        "ENV": env,
        "DATABASE_URL": _mask(database_url) or masked_db,
        "ALPACA_API_KEY": _mask(alpaca_key),
        "ALPACA_API_SECRET": _mask(alpaca_secret),
        "ALPACA_FEED": alpaca_feed,
        "WATCHLIST_SOURCE": watchlist_source or "textlist",
        "TEXTLIST_BACKENDS": textlist_backends,
    }

    return {
        "status": status,
        "environment": env,
        "env": env_dump,
        "checks": checks,
        "validation": checks,
        "config": config,
        "counters": {"watchlist_sources": get_watchlist_counters()},
    }
