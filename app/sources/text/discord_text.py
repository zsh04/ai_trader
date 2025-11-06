"""
Discord text backend stub for watchlist ingestion.

Reads a comma-separated environment variable (DISCORD_SAMPLE_SYMBOLS),
parses it using the shared textlist extractor, and returns a normalized list
of ticker symbols respecting the caller's max_symbols limit.
"""

from __future__ import annotations

import os
from typing import List

from app.sources.textlist_source import extract_symbols


def get_symbols(*, max_symbols: int | None = None) -> List[str]:
    """
    Return deduplicated, uppercased symbols parsed from DISCORD_SAMPLE_SYMBOLS.

    Args:
        max_symbols: optional maximum number of symbols to return.
    """
    raw = os.getenv("DISCORD_SAMPLE_SYMBOLS", "")
    if not raw:
        return []

    limit = max_symbols if isinstance(max_symbols, int) and max_symbols > 0 else None
    symbols = extract_symbols(raw, max_symbols=limit or 1000)

    seen: set[str] = set()
    deduped: List[str] = []
    for sym in symbols:
        ticker = (sym or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        deduped.append(ticker)
        if limit is not None and len(deduped) >= limit:
            break

    if limit is not None and len(deduped) > limit:
        return deduped[:limit]
    return deduped


__all__ = ["get_symbols"]
