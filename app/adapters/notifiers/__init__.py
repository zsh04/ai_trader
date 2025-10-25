# Notification adapters (Telegram, email, etc.)
"""
Notification adapters package.
Centralized entry point for all outbound notifications — Telegram, Email, Discord, etc.
"""

import logging

logger = logging.getLogger("notifiers")

from app.adapters.notifiers.telegram_notifier import TelegramNotifier  # noqa: F401
# from app.adapters.notifiers.email_notifier import EmailNotifier       # optional future import
# from app.adapters.notifiers.discord_notifier import DiscordNotifier   # optional future import

__all__ = ["TelegramNotifier"]