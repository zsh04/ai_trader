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
    """
    Checks if the Finviz source is ready.

    Returns:
        bool: True if the source is ready, False otherwise.
    """
    return _FINVIZ_OK


def fetch_symbols(
    preset: str = "Top Gainers",
    filters: Optional[List[str]] = None,
    max_symbols: int = 50,
) -> List[str]:
    """
    Fetches symbols from Finviz.

    Args:
        preset (str): The Finviz preset to use.
        filters (Optional[List[str]]): A list of Finviz filters to use.
        max_symbols (int): The maximum number of symbols to return.

    Returns:
        List[str]: A list of symbols.
    """
    if not _FINVIZ_OK:
        log.warning("finvizfinance not installed; returning []")
        return []

    try:
        s = Screener(filters=filters or [], tickers=[], order="price")
        if preset:
            s.set_filter(signal=preset)
        df = s.get_screen_df()

        if hasattr(df, "get"):
            tickers = df.get("Ticker", [])
        elif isinstance(df, list):
            tickers = [row.get("Ticker") for row in df if isinstance(row, dict)]
        else:
            log.warning("Unexpected Finviz schema type: %s", type(df))
            tickers = []

        symbols = [str(t).upper().strip() for t in tickers if t]
        symbols = [s for s in symbols if s.isalpha() and 1 <= len(s) <= 5]

        log.info("Finviz returned %d tickers for preset='%s'", len(symbols), preset)
        return symbols[:max_symbols]
    except Exception as e:
        log.exception("Finviz fetch failed: %s", e)
        return []


def get_symbols(*, max_symbols: int | None = None) -> List[str]:
    """
    Gets symbols from Finviz.

    Args:
        max_symbols (int | None): The maximum number of symbols to return.

    Returns:
        List[str]: A list of symbols.
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
