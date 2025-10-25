# app/sources/textlist_source.py
from __future__ import annotations
import re
from typing import List

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")

def extract_symbols(raw: str, max_symbols: int = 100) -> List[str]:
    # accept AAPL, TSLA, NVDA or comma/space separated lines
    syms = [m.group(0) for m in _TICKER_RE.finditer(raw)]
    # basic clean: exclude common words accidentally matching (e.g., “FOR”, “AND”)
    blacklist = {"FOR", "AND", "THE", "ALL", "WITH"}
    out = [s for s in syms if s not in blacklist]
    return out[:max_symbols]