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
from app.api.routes.tasks import public_router, tasks_router


def get_api_router() -> APIRouter:
    """Create and return the top-level API router including sub-routers.

    This keeps `main.py` minimal and allows conditional inclusion of optional
    routers without import-time failures when those modules are absent.
    """
    api = APIRouter()

    # Health / version endpoints (no prefix for convenience)
    api.include_router(health_router, tags=["health"])  # /health, /health/db, /version

    api.include_router(tasks_router, prefix="/tasks", tags=["tasks"])  # /tasks/*
    api.include_router(public_router, prefix="/watchlist", tags=["watchlist"])

    return api


__all__ = ["get_api_router"]
