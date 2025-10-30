from __future__ import annotations
import logging
import re
from typing import List

log = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:[.-][A-Z0-9]{1,3})?\b")
_BLACKLIST = {"FOR", "AND", "THE", "ALL", "WITH", "USA", "CEO", "ETF"}

def extract_symbols(raw: str, max_symbols: int = 100) -> List[str]:
    """
    Extract likely stock ticker symbols from a raw text block.

    Accepts comma-, space-, or newline-separated input.
    For example:
        "AAPL, TSLA, NVDA" → ["AAPL", "TSLA", "NVDA"]

    Parameters
    ----------
    raw : str
        Free-form text containing uppercase words or ticker-like tokens.
    max_symbols : int, optional
        Maximum number of tickers to return (default: 100).

    Returns
    -------
    list[str]
        A list of cleaned, uppercase ticker symbols.
    """
    if not raw:
        log.debug("extract_symbols called with empty input.")
        return []

    raw_clean = raw.replace(",", " ").upper().strip()
    syms = [m.group(0) for m in _TICKER_RE.finditer(raw_clean)]

    out = [s for s in syms if s not in _BLACKLIST]
    out = [s for s in out if 1 <= len(s) <= 5 and s.isalpha()]

    unique = list(dict.fromkeys(out))  # preserve order, dedupe
    log.info("Extracted %d symbols: %s", len(unique), unique[:10])
    return unique[:max_symbols]

# --- Compatibility wrapper for unified watchlist interface ---
def get_symbols(preferred: bool = False, max_symbols: int = 100) -> list[str]:
    """
    Returns a normalized list of tickers from textlist source.
    The `preferred` flag is ignored (present for interface consistency).
    """
    raw = os.getenv("TEXTLIST_SYMBOLS", "")
    return extract_symbols(raw, max_symbols=max_symbols)

__all__ = ["extract_symbols", "get_symbols"]
