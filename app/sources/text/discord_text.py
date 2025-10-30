"""
Discord text backend stub for watchlist ingestion.

Reads a comma-separated environment variable (DISCORD_SAMPLE_SYMBOLS),
parses it using the shared textlist extractor, and returns a normalized list
of ticker symbols respecting the caller's max_symbols limit.
"""
from __future__ import annotations

import os
import logging
from typing import List, Optional

from app.sources.textlist_source import extract_symbols
from app.utils.logging import logger as app_logger

logger = app_logger if 'app_logger' in globals() else logging.getLogger(__name__)


def get_symbols(*, max_symbols: Optional[int] = None) -> List[str]:
    """
    Return deduplicated, uppercased symbols parsed from DISCORD_SAMPLE_SYMBOLS.

    Args:
        max_symbols: Optional maximum number of symbols to return.

    Returns:
        List of unique, uppercased ticker symbols respecting max_symbols limit.
    """
    raw = os.getenv("DISCORD_SAMPLE_SYMBOLS", "")
    if not raw:
        logger.debug("DISCORD_SAMPLE_SYMBOLS environment variable is empty or not set.")
        return []

    logger.debug(f"Raw DISCORD_SAMPLE_SYMBOLS content: {raw}")

    limit = max_symbols if isinstance(max_symbols, int) and max_symbols > 0 else None
    try:
        symbols = extract_symbols(raw, max_symbols=limit or 1000)
    except Exception as e:
        logger.error(f"Error extracting symbols from DISCORD_SAMPLE_SYMBOLS: {e}")
        return []

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for sym in symbols:
        ticker = (sym or "").strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            deduped.append(ticker)
            if limit is not None and len(deduped) >= limit:
                break

    if limit is not None and len(deduped) > limit:
        deduped = deduped[:limit]

    logger.debug(f"Returning {len(deduped)} symbols after deduplication and applying limit.")
    return deduped


__all__ = ["get_symbols"]
