from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from app.utils.env import ALPACA_DATA_BASE_URL, ALPACA_FEED
from app.utils.http import alpaca_headers, http_get
from app.utils.normalize import bars_to_map

__all__ = [
    "snapshots",
    "bars",
    "minute_bars",
    "day_bars",
    "latest_closes",
]


def _normalize_symbols(symbols: List[str]) -> List[str]:
    """Uppercase, trim, and de-duplicate while preserving order."""
    seen = set()
    out: List[str] = []
    for s in symbols:
        if not s:
            continue
        u = s.strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


# Alpaca multi-symbol endpoints have practical payload/throughput limits.
# Keep batches conservative to avoid HTTP 413/timeout issues.
_CHUNK_SIZE = 50


def _chunk_symbols(symbols: List[str], n: int = _CHUNK_SIZE) -> List[List[str]]:
    syms = _normalize_symbols(symbols)
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
            logger.warning(
                "alpaca snapshots feed={} status={} err={} batch={}",
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
    # If everything came back empty, provide a helpful hint.
    if not out and symbols:
        logger.warning(
            "alpaca snapshots returned empty for all symbols (feed={}). "
            "Check your Alpaca data plan (IEX vs SIP) and market hours.",
            feed,
        )
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
        timeframe: e.g. "1Min", "5Min", "15Min", "1Hour", "1Day" (Alpaca formats).
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
            logger.warning(
                "alpaca bars feed={} tf={} limit={} status={} err={} batch={}",
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
    # If all returned series are empty, surface a clear hint for debugging.
    if result and not any(seq for seq in result.values()):
        logger.warning(
            "alpaca bars returned empty for all symbols (feed={}, tf={}). "
            "Verify Alpaca data subscription and market hours.",
            feed,
            timeframe,
        )
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
        except (TypeError, ValueError) as exc:  # nosec B110 - log parse failure
            logger.debug(
                "alpaca latest_closes parse error sym={} err={}",
                sym,
                exc,
            )
    return out


def latest_trades_from_snapshots(snaps: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """Extract the last trade price from snapshot responses.
    Falls back to last quote if trade is missing. Returns {SYM: price}.
    """
    out: Dict[str, float] = {}
    for sym, s in (snaps or {}).items():
        if not s:
            continue
        try:
            trade = s.get("latestTrade") or {}
            quote = s.get("latestQuote") or {}
            p = float(trade.get("p") or quote.get("bp") or 0)
            if p > 0:
                out[sym.upper()] = p
        except Exception as exc:
            logger.debug(
                "alpaca latest_trades_from_snapshots parse failure {}: {}", sym, exc
            )
            continue
    if not out:
        logger.warning("no valid latest trade prices extracted from snapshots")
    return out


def has_data(data_map: Optional[Dict[str, Any]]) -> bool:
    """Return True if any non-empty series or map has data."""
    if not data_map:
        return False
    for v in data_map.values():
        if v:
            return True
    return False
