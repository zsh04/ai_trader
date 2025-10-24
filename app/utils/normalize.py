from __future__ import annotations

from typing import Any, Dict, List


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
