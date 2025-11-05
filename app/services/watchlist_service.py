# app/services/watchlist_service.py
from __future__ import annotations

from typing import Iterable, List, Optional

# Existing sources you already have
from app.source.textlist_source import get_symbols as textlist_symbols
from app.services.watchlist_sources import (
    fetch_alpha_vantage_symbols,
    fetch_finnhub_symbols,
    fetch_twelvedata_symbols,
)


def _dedupe(seq: Iterable[str]) -> List[str]:
    """De-dupe while preserving order (case-insensitive)."""
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
    Return a deduped list of symbols from the requested source.

    source: 'auto' | 'alpha' | 'finnhub' | 'textlist' | 'manual'
    scanner: optional scanner name (e.g., 'top_gainers'); handled by source
    limit: cap result length
    sort: 'alpha' or None
    """
    source = (source or "auto").strip().lower()
    scanner = (scanner or "").strip() or None
    sort = (sort or "").strip().lower() or None

    symbols: List[str] = []

    def _fetch_alpha() -> List[str]:
        try:
            return list(fetch_alpha_vantage_symbols(scanner=scanner))
        except Exception:
            return []

    def _fetch_finnhub() -> List[str]:
        try:
            return list(fetch_finnhub_symbols(scanner=scanner))
        except Exception:
            return []

    def _fetch_twelvedata() -> List[str]:
        try:
            return list(fetch_twelvedata_symbols(scanner=scanner))
        except Exception:
            return []

    def _fetch_textlist() -> List[str]:
        try:
            return list(textlist_symbols(scanner=scanner))
        except Exception:
            return []

    if source == "alpha":
        symbols = _fetch_alpha()
    elif source == "finnhub":
        symbols = _fetch_finnhub()
    elif source == "textlist":
        symbols = _fetch_textlist()
    else:
        # auto: Alpha Vantage, fallback to Finnhub then textlist, then Twelve Data
        symbols = _fetch_alpha()
        if not symbols:
            symbols = _fetch_finnhub()
        if not symbols:
            symbols = _fetch_textlist()
        if not symbols:
            symbols = _fetch_twelvedata()

    symbols = _dedupe(symbols)

    if sort == "alpha":
        symbols = sorted(symbols)

    if limit is not None and limit > 0:
        symbols = symbols[:limit]

    return symbols
