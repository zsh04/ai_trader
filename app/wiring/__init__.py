# app/wiring/__init__.py
from __future__ import annotations
from fastapi import APIRouter

# Create a top-level router and include telegram
router = APIRouter()

# Re-export dependency factory (used in tests or elsewhere)
from app.adapters.notifiers.telegram import build_client_from_env

# Mount the webhook routes at /telegram
from app.api.routes.telegram import router as telegram_router  # noqa: E402
# Avoid double prefix; the telegram router already has prefix="/telegram"
router.include_router(telegram_router)


def TelegramDep():
    return build_client_from_env()


def get_telegram():
    # Keep a stable import path for existing code
    return build_client_from_env()
