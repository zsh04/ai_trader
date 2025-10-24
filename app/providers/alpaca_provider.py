from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.utils.env import ALPACA_DATA_BASE_URL, ALPACA_FEED
from app.utils.http import alpaca_headers, http_get
from app.utils.normalize import bars_to_map

log = logging.getLogger(__name__)

# Alpaca multi-symbol endpoints have practical payload/throughput limits.
# Keep batches conservative to avoid HTTP 413/timeout issues.
_CHUNK_SIZE = 50


def _chunk_symbols(symbols: List[str], n: int = _CHUNK_SIZE) -> List[List[str]]:
    syms = [s.strip().upper() for s in symbols if s and s.strip()]
    return [syms[i : i + n] for i in range(0, len(syms), n)]


def snapshots(
    symbols: List[str], feed: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """Fetch latest snapshots for multiple symbols.

    - Batches requests to avoid API limits.
    - Returns a flat dict {SYMBOL: snapshot_dict}.
    - If an error occurs for a batch, logs and continues (best-effort).
    """
    feed = feed or ALPACA_FEED
    batches = _chunk_symbols(symbols)
    if not batches:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for batch in batches:
        url = f"{ALPACA_DATA_BASE_URL}/stocks/snapshots"
        params = {"symbols": ",".join(batch), "feed": feed}
        status, data = http_get(url, params, headers=alpaca_headers())
        if status != 200:
            err = (data or {}).get("message") or (data or {}).get("error")
            log.warning(
                "alpaca snapshots feed=%s status=%s err=%s batch=%s",
                feed,
                status,
                err,
                ",".join(batch),
            )
            continue
        snaps = (data or {}).get("snapshots") or {}
        for k, v in snaps.items():
            if not k:
                continue
            out[k.upper()] = v or {}
    return out


def bars(
    symbols: List[str],
    timeframe: str,
    limit: int = 1,
    feed: Optional[str] = None,
    adjustment: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch bars for multiple symbols.

    Args:
        timeframe: e.g. "1Min", "5Min", "15Min", "1Hour", "1Day".
        limit: number of bars per symbol.
        feed: "iex" (paper/free) or "sip" (paid), defaults to env.
        adjustment: raw/split/dividend (passed-through if provided).

    Returns:
        Dict[SYMBOL, List[bar_dict]] — missing symbols map to empty lists.
    """
    feed = feed or ALPACA_FEED
    batches = _chunk_symbols(symbols)
    if not batches:
        return {}

    result: Dict[str, List[Dict[str, Any]]] = {
        s.strip().upper(): [] for s in symbols if s
    }
    for batch in batches:
        url = f"{ALPACA_DATA_BASE_URL}/stocks/bars"
        params: Dict[str, Any] = {
            "symbols": ",".join(batch),
            "timeframe": timeframe,
            "limit": int(limit),
            "feed": feed,
        }
        if adjustment:
            params["adjustment"] = adjustment
        status, data = http_get(url, params, headers=alpaca_headers())
        if status != 200:
            err = (data or {}).get("message") or (data or {}).get("error")
            log.warning(
                "alpaca bars feed=%s tf=%s limit=%s status=%s err=%s batch=%s",
                feed,
                timeframe,
                limit,
                status,
                err,
                ",".join(batch),
            )
            # keep empty lists for this batch
            continue
        part = bars_to_map((data or {}).get("bars"), batch)
        # merge into result (append to list per symbol)
        for sym, seq in part.items():
            if not isinstance(seq, list):
                continue
            result.setdefault(sym, []).extend(seq)
    return result


def minute_bars(
    symbols: List[str],
    limit: int = 1,
    feed: Optional[str] = None,
    adjustment: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    return bars(
        symbols, timeframe="1Min", limit=limit, feed=feed, adjustment=adjustment
    )


def day_bars(
    symbols: List[str],
    limit: int = 1,
    feed: Optional[str] = None,
    adjustment: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    return bars(
        symbols, timeframe="1Day", limit=limit, feed=feed, adjustment=adjustment
    )


def latest_closes(symbols: List[str], feed: Optional[str] = None) -> Dict[str, float]:
    """Convenience: fetch latest daily close for each symbol.
    Uses `day_bars(..., limit=1)` and extracts `c`.
    """
    m = day_bars(symbols, limit=1, feed=feed)
    out: Dict[str, float] = {}
    for sym, seq in m.items():
        if not seq:
            continue
        try:
            c = float(seq[-1].get("c") or 0)
            if c > 0:
                out[sym] = c
        except Exception:
            pass
    return out
