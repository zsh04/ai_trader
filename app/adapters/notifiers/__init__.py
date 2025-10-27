# app/adapters/notifiers/__init__.py
"""
Notifier adapters package.

Exports Telegram notifier utilities without pulling in non-existent modules.
"""

from .telegram import TelegramClient, format_watchlist_message, send_watchlist

__all__ = [
    "TelegramClient",
    "format_watchlist_message",
    "send_watchlist",
]