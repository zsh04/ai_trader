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

from app.api.routes import mount as mount_routes


def get_api_router() -> APIRouter:
    """Return an APIRouter wired with all routes."""
    api = APIRouter()
    mount_routes(api)
    return api


__all__ = ["get_api_router"]
