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
from typing import Any
from .health import router as health_router
#from .telegram import router as telegram_router
from .tasks import router as tasks_router
from fastapi import APIRouter, FastAPI

router = APIRouter()
router.include_router(health_router, prefix="/health", tags=["health"])
#router.include_router(telegram_router, prefix="/telegram", tags=["telegram"])
router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])

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


# Try to aggregate sibling routers. Only include what exists.
_include_optional("app.api.routes.health")
#_include_optional("app.api.routes.telegram")
_include_optional("app.api.routes.tasks")


def mount(app: FastAPI) -> None:
    """Convenience helper to attach all aggregated routes to the app."""
    app.include_router(router)