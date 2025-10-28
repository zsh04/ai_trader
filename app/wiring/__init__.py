"""
Wiring package initializer.

Re-exports the `telegram_router` module and key symbols so both of these work:

    from app.wiring import telegram_router as router
    from app.wiring import router as telegram_router

Also exposes `get_telegram` and `TelegramDep` when present.
"""
from __future__ import annotations

from typing import Any
from . import telegram_router as _telegram_router

# Re-export the submodule itself
telegram_router = _telegram_router

# Convenience aliases expected across the codebase/tests
router = getattr(_telegram_router, "router", None)
get_telegram = getattr(_telegram_router, "get_telegram", None)
TelegramDep = getattr(_telegram_router, "TelegramDep", None)

def __getattr__(name: str) -> Any:  # lazy proxy to telegram_router
    return getattr(_telegram_router, name)

__all__ = [
    "telegram_router",
    "router",
    "get_telegram",
    "TelegramDep",
]