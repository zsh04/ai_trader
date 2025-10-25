# app/providers/__init__.py
"""
Provider façade.

This module re-exports the most commonly used functions from concrete providers
(Alpaca, Yahoo) so call sites can import from `app.providers` without caring
about the specific backend.

Example:
    from app.providers import intraday_last, latest_close, snapshots_last
"""

from __future__ import annotations

# --- Alpaca -----------------------------------------------------------------
# Only import if the module exists and its env is configured by the caller.
try:
    from .alpaca_provider import (  # type: ignore
        snapshots_last,        # Dict[str, float] best-effort last (trade/nbbo/1m)
        intraday_bars,         # Dict[str, List[bar]] intraday OHLCV
        daily_bars,            # Dict[str, List[bar]] daily OHLCV
        ensure_feed,           # Tuple(feed_name, is_enabled)
        is_sip_enabled,        # bool
        is_iex_enabled,        # bool
    )
    _ALPACA_AVAILABLE = True
except Exception:  # pragma: no cover - keep import failure non-fatal
    _ALPACA_AVAILABLE = False

# --- Yahoo ------------------------------------------------------------------
try:
    from .yahoo_provider import (  # type: ignore
        intraday_last,         # Dict[str, float]
        latest_close,          # Dict[str, float]
        latest_volume,         # Dict[str, int]
        get_history_daily,     # pd.DataFrame[open,high,low,close,volume]
    )
    _YAHOO_AVAILABLE = True
except Exception:  # pragma: no cover
    _YAHOO_AVAILABLE = False

__all__ = [
    # Alpaca
    "snapshots_last",
    "intraday_bars",
    "daily_bars",
    "ensure_feed",
    "is_sip_enabled",
    "is_iex_enabled",
    # Yahoo
    "intraday_last",
    "latest_close",
    "latest_volume",
    "get_history_daily",
    # availability flags
    "_ALPACA_AVAILABLE",
    "_YAHOO_AVAILABLE",
]