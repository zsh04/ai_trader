"""
Top-level API router factory.

Main app should import `get_api_router()` and mount it, e.g.:

    from app.api import get_api_router
    app.include_router(get_api_router())

You can optionally mount under a prefix:

    app.include_router(get_api_router(), prefix="/api")
"""

from __future__ import annotations

from fastapi import APIRouter

# Required routes
from app.api.routes.health import router as health_router

# Optional routes (present in most setups but imported defensively)
try:  # telegram commands/webhook
    from app.api.routes.telegram import router as telegram_router  # type: ignore
except Exception:  # pragma: no cover - survive partial installations
    telegram_router = None  # type: ignore

try:  # watchlist/build tasks and utilities
    from app.api.routes.tasks import router as tasks_router  # type: ignore
except Exception:  # pragma: no cover
    tasks_router = None  # type: ignore


def get_api_router() -> APIRouter:
    """Create and return the top-level API router including sub-routers.

    This keeps `main.py` minimal and allows conditional inclusion of optional
    routers without import-time failures when those modules are absent.
    """
    api = APIRouter()

    # Health / version endpoints (no prefix for convenience)
    api.include_router(health_router, tags=["health"])  # /health, /health/db, /version

    if telegram_router is not None:
        api.include_router(
            telegram_router, prefix="/telegram", tags=["telegram"]
        )  # /telegram/*

    if tasks_router is not None:
        api.include_router(tasks_router, prefix="/tasks", tags=["tasks"])  # /tasks/*

    return api


__all__ = ["get_api_router"]
