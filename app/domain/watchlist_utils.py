from __future__ import annotations

from typing import List


def normalize_symbols(items: list[str]) -> List[str]:
    """
    Normalizes and deduplicates a list of symbols.

    Args:
        items (list[str]): A list of symbols.

    Returns:
        List[str]: A normalized and deduplicated list of symbols.
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
