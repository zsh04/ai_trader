# app/source/finviz_source.py
from __future__ import annotations

import os
from typing import List, Optional

from app.sources.finviz_source import fetch_symbols as _fetch_symbols

__all__ = ["get_symbols"]


def get_symbols(
    preset: str | None = None,
    filters: Optional[List[str]] = None,
    max_symbols: int = 50,
) -> List[str]:
    """
    Return a list of Finviz symbols using the shared ``fetch_symbols`` helper.

    Environment variable ``FINVIZ_WATCHLIST_PRESET`` can override the preset.
    """
    resolved_preset = preset or os.getenv("FINVIZ_WATCHLIST_PRESET", "Top Gainers")
    return _fetch_symbols(
        preset=resolved_preset,
        filters=filters,
        max_symbols=max_symbols,
    )
