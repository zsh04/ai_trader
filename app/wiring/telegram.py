from __future__ import annotations

from typing import Generator

from app.adapters.notifiers.telegram import TelegramClient
from app.utils.env import (
    TELEGRAM_ALLOWED_USER_IDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_TIMEOUT_SECS,
    TELEGRAM_WEBHOOK_SECRET,
)

_client: TelegramClient | None = None


def get_telegram() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(
            bot_token=TELEGRAM_BOT_TOKEN,
            allowed_users=TELEGRAM_ALLOWED_USER_IDS,
            webhook_secret=TELEGRAM_WEBHOOK_SECRET,
            timeout=TELEGRAM_TIMEOUT_SECS,
        )
    return _client


# Optional DI helper for FastAPI endpoints
def TelegramDep() -> Generator[TelegramClient, None, None]:
    yield get_telegram()
