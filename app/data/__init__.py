

"""
Data adapters and external data providers (Alpaca, Yahoo Finance, etc.)
Provides unified APIs for fetching and caching market data across sources.
"""

from .data_client import (
    batch_latest_ohlcv,
    data_health,
)