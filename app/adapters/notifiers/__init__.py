# app/adapters/notifiers/__init__.py
"""
Notifier adapters for outbound integrations (Telegram, Email, Slack, etc.)
"""
from .telegram import TelegramClient, build_client_from_env
