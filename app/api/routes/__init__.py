"""
Aggregate API routes for AI Trader.

This module simply assembles sub-routers from sibling modules
(e.g., `health.py`, `telegram.py`, `tasks.py`).

Usage in app.main:
    from app.api.routes import mount as mount_routes
    mount_routes(app)

All imports are lazy/optional: missing modules are skipped so you
can iterate incrementally.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from .health import router as health_router
from .telegram import router as telegram_router
from .watchlists import router as watchlists_router

router = APIRouter()
router.include_router(health_router, prefix="/health", tags=["health"])
router.include_router(watchlists_router, prefix="/watchlists", tags=["watchlists"])
router.include_router(telegram_router, prefix="/telegram", tags=["telegram"])


def _include_optional(module_path: str, attr: str = "router") -> None:
    """Try to import a module and include its router if present.

    This avoids hard dependencies during refactors; if a submodule is missing,
    we simply skip it.
    """
    try:
        mod = __import__(module_path, fromlist=[attr])
        sub_router = getattr(mod, attr, None)
        if sub_router is not None:
            router.include_router(sub_router)
    except Exception:
        # Intentionally swallow import errors to keep app boot resilient
        pass


_include_optional("app.api.routes.health")


def mount(app: FastAPI) -> None:
    """Convenience helper to attach all aggregated routes to the app."""
    app.include_router(router)
