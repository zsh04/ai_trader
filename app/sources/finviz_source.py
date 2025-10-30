from __future__ import annotations

import logging
import os
from typing import List, Optional

try:
    from finvizfinance.screener import Screener

    _FINVIZ_OK = True
except Exception:
    _FINVIZ_OK = False

log = logging.getLogger(__name__)


def is_ready() -> bool:
    """Return True if Finviz source is operational and importable."""
    return _FINVIZ_OK


def fetch_symbols(
    preset: str = "Top Gainers",
    filters: Optional[List[str]] = None,
    max_symbols: int = 50,
) -> List[str]:
    """
    Fetch ticker symbols from Finviz using its public Screener API.

    Parameters
    ----------
    preset : str, optional
        Finviz preset signal name (e.g., "Top Gainers", "Unusual Volume").
    filters : list[str], optional
        Finviz filter codes (e.g., ["sh_avgvol_o3000", "ta_perf_4w20o"]).
    max_symbols : int, optional
        Maximum number of tickers to return, by default 50.

    Returns
    -------
    list[str]
        A list of uppercase ticker symbols (AAPL, TSLA, etc.).
    """
    if not _FINVIZ_OK:
        log.warning("finvizfinance not installed; returning []")
        return []

    try:
        s = Screener(filters=filters or [], tickers=[], order="price")
        if preset:
            s.set_filter(signal=preset)
        df = s.get_screen_df()

        # Support both DataFrame and list-of-dicts returns
        if hasattr(df, "get"):
            tickers = df.get("Ticker", [])
        elif isinstance(df, list):
            tickers = [row.get("Ticker") for row in df if isinstance(row, dict)]
        else:
            log.warning("Unexpected Finviz schema type: %s", type(df))
            tickers = []

        # Normalize and filter symbols
        symbols = [str(t).upper().strip() for t in tickers if t]
        symbols = [s for s in symbols if s.isalpha() and 1 <= len(s) <= 5]

        log.info("Finviz returned %d tickers for preset='%s'", len(symbols), preset)
        return symbols[:max_symbols]
    except Exception as e:
        log.exception("Finviz fetch failed: %s", e)
        return []


# --- Compatibility wrapper for unified watchlist interface ---
def get_symbols(preferred: bool = False, max_symbols: int = 100) -> list[str]:
    """
    Unified API: returns top tickers from Finviz screener.
    `preferred` flag reserved for future use (e.g., preferred presets).
    """
    preset = os.getenv("FINVIZ_PRESET", "most-active")
    filters = os.getenv("FINVIZ_FILTERS", "cap_large,sh_avgvol_o1000")
    try:
        return fetch_symbols(preset=preset, filters=filters, max_symbols=max_symbols)
    except Exception as exc:
        logger.warning(f"[FinvizSource] Failed to fetch symbols: {exc}")
        return []

__all__ = ["fetch_symbols", "get_symbols"]
