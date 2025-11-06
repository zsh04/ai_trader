from __future__ import annotations

from fastapi import APIRouter

from app.adapters.notifiers.telegram import (
    build_client_from_env as build_client_from_env,
)
from app.api.routes.telegram import (
    TelegramDep as TelegramDep,
)
from app.api.routes.telegram import (
    get_telegram as get_telegram,
)
from app.api.routes.telegram import (
    router as telegram_router,
)

router = APIRouter()

# Avoid double prefix; the telegram router already has prefix="/telegram"
router.include_router(telegram_router)

__all__ = ["router", "TelegramDep", "get_telegram", "build_client_from_env"]
