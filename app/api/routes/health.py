from __future__ import annotations
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict
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
