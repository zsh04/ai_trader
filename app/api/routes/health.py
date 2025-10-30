from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Any, Dict
import os
from urllib.parse import urlparse
from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter

try:
    from app import __version__ as APP_VERSION  # set in app/__init__.py
except Exception:  # pragma: no cover
    try:
        from app.utils import env as ENV  # fallback to env var if present

        APP_VERSION = getattr(ENV, "APP_VERSION", "0.1.0")
    except Exception:
        APP_VERSION = "0.1.0"

from app.adapters.db.postgres import ping
from app.api.routes.tasks import get_build_counters
from app.domain.watchlist_service import get_counters as get_watchlist_counters

router = APIRouter(tags=["health"])


@router.get("")
async def health() -> Dict[str, Any]:
    """Legacy health endpoint (mirrors /health/live)."""
    return await health_live()


@router.get("/live")
async def health_live() -> Dict[str, Any]:
    """Lightweight liveness probe."""
    return {"ok": True, "service": "ai-trader", "version": APP_VERSION}


@router.get("/db")
async def health_db() -> Dict[str, Any]:
    """Database connectivity probe with simple latency measurement.
    Keeps response compact so it can be used as a readiness probe.
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
    """Lightweight readiness probe with UTC timestamp."""
    return {"status": "ok", "utc": datetime.now(timezone.utc).isoformat()}

@router.get("/market")
async def health_market():
    import os, logging
    from app.adapters.market.alpaca_client import ping_alpaca, AlpacaPingError

    feed = os.getenv("ALPACA_DATA_FEED", "").lower() or "iex"  # default
    try:
        ok, meta = await run_in_threadpool(lambda: ping_alpaca(feed=feed, timeout_sec=4.0))
        return {"status": "ok" if ok else "degraded", "feed": feed, "meta": meta}
    except AlpacaPingError as e:
        logging.warning("market ping failed: %s", e)
        return {"status": "degraded", "feed": feed, "reason": str(e)}


@router.get("/version")
async def version() -> Dict[str, str]:
    """Expose application version for diagnostics and CI smoke tests."""
    return {"version": APP_VERSION}


def _mask(value: str | None) -> str:
    if not value:
        return ""
    prefix = 2
    suffix = 4
    stripped = value.strip()
    if len(stripped) <= prefix + suffix:
        if len(stripped) <= 2:
            return stripped[:1] + "*" * max(len(stripped) - 1, 0)
        return stripped[:prefix] + "*" * (len(stripped) - prefix)
    return stripped[:prefix] + "*" * (len(stripped) - prefix - suffix) + stripped[-suffix:]


@router.get("/config")
async def health_config() -> Dict[str, Any]:
    env = os.getenv("ENV", "dev").lower()

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat = os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "")
    database_url = os.getenv("DATABASE_URL", "")
    alpaca_key = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret = os.getenv("ALPACA_API_SECRET", "")
    alpaca_feed = os.getenv("ALPACA_FEED", "iex")
    watchlist_source = os.getenv("WATCHLIST_SOURCE", "")
    textlist_backends = os.getenv("TEXTLIST_BACKENDS", "")

    has_telegram = bool(telegram_token)
    has_db = bool(database_url)
    has_alpaca = bool(alpaca_key and alpaca_secret)

    parsed = urlparse(database_url) if database_url else None
    db_host = parsed.hostname if parsed else ""
    db_name = parsed.path.lstrip("/") if parsed else ""
    masked_db = ""
    if db_host or db_name:
        masked_db = f"{_mask(db_host)}/{_mask(db_name)}".strip("/")

    config = {
        "telegram_bot_token": _mask(telegram_token),
        "telegram_default_chat_id": telegram_chat,
        "database_url": masked_db or _mask(database_url),
        "alpaca_api_key": _mask(alpaca_key),
        "alpaca_feed": alpaca_feed,
        "watchlist_source": watchlist_source or "textlist",
        "textlist_backends": textlist_backends,
    }

    checks = {
        "has_telegram_token": has_telegram,
        "has_db_url": has_db,
        "has_alpaca_keys": has_alpaca,
    }

    # Determine overall status
    required_ok = has_telegram and has_db and has_alpaca
    status = "ok"
    if env == "prod" and not required_ok:
        status = "degraded"

    env_dump = {
        "ENV": env,
        "TELEGRAM_BOT_TOKEN": _mask(telegram_token),
        "TELEGRAM_DEFAULT_CHAT_ID": telegram_chat,
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
        "counters": {
            "watchlist_sources": get_watchlist_counters(),
            "watchlist_builds": get_build_counters(),
        },
    }
