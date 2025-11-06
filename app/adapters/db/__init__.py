"""
Database adapters namespace.

This package centralizes database-related adapters and connection utilities.
Each module inside should expose a clear interface for database operations,
such as fetching, writing, or managing cached data for AI Trader.
"""

import logging

logger = logging.getLogger(__name__)

logger.debug("Initialized database adapters package.")
