from __future__ import annotations
from typing import Iterable, List, Set
import logging

log = logging.getLogger(__name__)

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
    log.debug("dedupe_merge merged %d tickers (%d duplicates skipped)", len(out), len(seen) - len(out))
    return out