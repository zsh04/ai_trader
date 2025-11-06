from __future__ import annotations

import re
from typing import Any, Dict, List

_SMART_MAP = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u2032": "'",
    "\u2035": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
    "\u2033": '"',
    "\u2036": '"',
    "\u00ab": '"',
    "\u00bb": '"',
    "\u0060": "'",
    "\u00b4": "'",
}
_SMART_DASHES = {"\u2013", "\u2014", "\u2212"}
_KV_PATTERN = re.compile(r"--([A-Za-z0-9_-]+)=(?:\"([^\"]*)\"|'([^']*)'|([^\s]+))")


def normalize_quotes_and_dashes(text: str) -> str:
    """Normalize fancy quotes and dashes to plain ASCII variants."""
    if not text:
        return ""
    out = text
    for src, dst in _SMART_MAP.items():
        out = out.replace(src, dst)
    for dash in _SMART_DASHES:
        out = out.replace(dash, "--")
    return out


def parse_kv_flags(text: str) -> Dict[str, str]:
    """Extract --key=value pairs handling smart quotes/dashes."""
    cleaned = normalize_quotes_and_dashes(text or "")
    matches = _KV_PATTERN.findall(cleaned)
    result: Dict[str, str] = {}
    for key, dq, sq, plain in matches:
        value = dq or sq or plain or ""
        result[key] = value.strip()
    return result


def parse_watchlist_args(text: str) -> Dict[str, Any]:
    """
    Parse CLI watchlist arguments into structured options.

    Args:
        text: Raw argument string (e.g. "--limit=10 --title='Custom' AAPL").

    Returns:
        Dict containing symbols, limit, session_hint, title, include_filters.
    """
    import shlex

    opts: Dict[str, Any] = {
        "symbols": [],
        "limit": None,
        "session_hint": None,
        "title": None,
        "include_filters": None,
    }
    raw = (text or "").strip()
    if not raw:
        return opts

    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()

    for part in parts:
        if part.startswith("--limit="):
            try:
                opts["limit"] = int(part.split("=", 1)[1])
            except ValueError:
                continue
        elif part.startswith("--session="):
            opts["session_hint"] = part.split("=", 1)[1]
        elif part.startswith("--title="):
            opts["title"] = part.split("=", 1)[1].strip('"').strip("'")
        elif part in ("--filters", "--no-filters"):
            opts["include_filters"] = part == "--filters"
        elif not part.startswith("--"):
            opts["symbols"].append(part.replace(",", " ").strip().upper())

    # Split comma-delimited entries that may have slipped through
    expanded: List[str] = []
    for sym in opts["symbols"]:
        expanded.extend([s for s in sym.split() if s])
    opts["symbols"] = expanded
    return opts


def bars_to_map(bars_obj: Any, symbols: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize Alpaca v2 bars payload into {SYM: [bar,...]} regardless of shape:
      - list of bar dicts (with 'S' or 'T' for symbol), or
      - dict {SYM: [bar,...]}
    """
    out: Dict[str, List[Dict[str, Any]]] = {s: [] for s in symbols}
    if isinstance(bars_obj, list):
        for b in bars_obj:
            if not isinstance(b, dict):
                continue
            sym = (b.get("S") or b.get("T") or "").upper()
            if sym:
                out.setdefault(sym, []).append(b)
    elif isinstance(bars_obj, dict):
        for k, v in bars_obj.items():
            sym = (k or "").upper()
            if not sym:
                continue
            seq = v if isinstance(v, list) else []
            out.setdefault(sym, []).extend([x for x in seq if isinstance(x, dict)])
    return out
