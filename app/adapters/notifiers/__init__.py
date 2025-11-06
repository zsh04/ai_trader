# app/adapters/notifiers/__init__.py
"""
Notifier adapters for outbound integrations (Telegram, Email, Slack, etc.)
"""

from .telegram import (
    TelegramClient as TelegramClient,
)
from .telegram import (
    build_client_from_env as build_client_from_env,
)

__all__ = ["TelegramClient", "build_client_from_env"]
