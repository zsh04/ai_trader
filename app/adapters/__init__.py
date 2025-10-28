"""Outbound adapters package for AI Trader.

Provides namespaced access to external integration layers:
- db: database adapters (e.g., PostgreSQL)
- notifiers: outbound message systems (e.g., Telegram)
- storage: blob/object storage helpers
- telemetry: logging and monitoring utilities

This module avoids eager imports to reduce side effects at app startup.
"""

# namespace for outbound adapters

__all__ = [
    "db",
    "notifiers",
    "storage",
    "telemetry",
]
