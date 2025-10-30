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
def get_symbols(*, max_symbols: int | None = None) -> List[str]:
    """
    Unified API: returns top tickers from Finviz screener.

    max_symbols limits the final deduplicated list if provided.
    """
    preset = os.getenv("FINVIZ_PRESET", "most-active")
    filters_raw = os.getenv("FINVIZ_FILTERS", "cap_large,sh_avgvol_o1000")
    filter_list = [f.strip() for f in filters_raw.split(",") if f.strip()] or None

    limit = max_symbols if isinstance(max_symbols, int) and max_symbols > 0 else None
    fetch_limit = limit if limit is not None else 100

    try:
        symbols = fetch_symbols(preset=preset, filters=filter_list, max_symbols=fetch_limit)
    except Exception as exc:
        log.warning("[FinvizSource] Failed to fetch symbols: %s", exc)
        return []

    seen: set[str] = set()
    result: List[str] = []
    for sym in symbols or []:
        ticker = (sym or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        result.append(ticker)
        if limit is not None and len(result) >= limit:
            break

    if limit is not None and len(result) > limit:
        return result[:limit]
    return result

__all__ = ["fetch_symbols", "get_symbols"]
