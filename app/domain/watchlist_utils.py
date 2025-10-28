# app/domain/watchlist_utils.py
from __future__ import annotations

from typing import List


def normalize_symbols(items: list[str]) -> List[str]:
    """
    Normalize and deduplicate symbol strings while preserving order.

    Steps:
    1. Strip leading/trailing whitespace.
    2. Uppercase the symbol.
    3. Drop blanks.
    4. Keep only the first occurrence of each symbol.
    """
    seen: set[str] = set()
    out: List[str] = []
    for raw in items or []:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out
