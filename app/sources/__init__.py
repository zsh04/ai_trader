# app/sources/__init__.py
from __future__ import annotations
from typing import Iterable, List, Set

def dedupe_merge(*groups: Iterable[str], limit: int | None = None) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for g in groups:
        for s in (g or []):
            u = s.strip().upper()
            if not u or u in seen:
                continue
            seen.add(u)
            out.append(u)
            if limit and len(out) >= limit:
                return out
    return out