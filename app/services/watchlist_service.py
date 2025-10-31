# app/services/watchlist_service.py
from __future__ import annotations

from typing import Iterable, List, Optional

from app.source.finviz_source import get_symbols as finviz_symbols
from app.source.textlist_source import get_symbols as textlist_symbols


def _dedupe(seq: Iterable[str]) -> List[str]:
    """
    Deduplicates a sequence of strings.

    Args:
        seq (Iterable[str]): A sequence of strings.

    Returns:
        List[str]: A deduplicated list of strings.
    """
    seen = set()
    out: List[str] = []
    for s in seq:
        k = s.strip().upper()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def build_watchlist(
    source: str = "auto",
    *,
    scanner: Optional[str] = None,
    limit: Optional[int] = None,
    sort: Optional[str] = None,
) -> List[str]:
    """
    Builds a watchlist from a given source.

    Args:
        source (str): The source to build the watchlist from.
        scanner (Optional[str]): The scanner to use.
        limit (Optional[int]): The maximum number of symbols to return.
        sort (Optional[str]): The sort order for the symbols.

    Returns:
        List[str]: A list of symbols.
    """
    source = (source or "auto").strip().lower()
    scanner = (scanner or "").strip() or None
    sort = (sort or "").strip().lower() or None

    symbols: List[str] = []

    def _fetch_finviz() -> List[str]:
        """
        Fetches symbols from Finviz.

        Returns:
            List[str]: A list of symbols.
        """
        try:
            return list(finviz_symbols(scanner=scanner))
        except Exception:
            return []

    def _fetch_textlist() -> List[str]:
        """
        Fetches symbols from a text list.

        Returns:
            List[str]: A list of symbols.
        """
        try:
            return list(textlist_symbols(scanner=scanner))
        except Exception:
            return []

    if source == "finviz":
        symbols = _fetch_finviz()
    elif source == "textlist":
        symbols = _fetch_textlist()
    else:
        symbols = _fetch_finviz()
        if not symbols:
            symbols = _fetch_textlist()

    symbols = _dedupe(symbols)

    if sort == "alpha":
        symbols = sorted(symbols)

    if limit is not None and limit > 0:
        symbols = symbols[:limit]

    return symbols
