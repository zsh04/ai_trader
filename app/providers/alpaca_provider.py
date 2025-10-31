from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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

log = logging.getLogger(__name__)


def _normalize_symbols(symbols: List[str]) -> List[str]:
    """
    Normalizes a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.

    Returns:
        List[str]: A normalized list of symbols.
    """
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


_CHUNK_SIZE = 50


def _chunk_symbols(symbols: List[str], n: int = _CHUNK_SIZE) -> List[List[str]]:
    """
    Chunks a list of symbols into smaller lists.

    Args:
        symbols (List[str]): A list of symbols.
        n (int): The size of each chunk.

    Returns:
        List[List[str]]: A list of lists of symbols.
    """
    syms = _normalize_symbols(symbols)
    return [syms[i : i + n] for i in range(0, len(syms), n)]


def snapshots(
    symbols: List[str], feed: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Fetches snapshots for a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.
        feed (Optional[str]): The data feed to use.

    Returns:
        Dict[str, Dict[str, Any]]: A dictionary of snapshots.
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
    if not out and symbols:
        log.warning(
            "alpaca snapshots returned empty for all symbols (feed=%s). "
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
    """
    Fetches bars for a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.
        timeframe (str): The timeframe to fetch.
        limit (int): The number of bars to fetch.
        feed (Optional[str]): The data feed to use.
        adjustment (Optional[str]): The adjustment to apply.

    Returns:
        Dict[str, List[Dict[str, Any]]]: A dictionary of bars.
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
            continue
        part = bars_to_map((data or {}).get("bars"), batch)
        for sym, seq in part.items():
            if not isinstance(seq, list):
                continue
            result.setdefault(sym, []).extend(seq)
    if result and not any(seq for seq in result.values()):
        log.warning(
            "alpaca bars returned empty for all symbols (feed=%s, tf=%s). "
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
    """
    Fetches minute bars for a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.
        limit (int): The number of bars to fetch.
        feed (Optional[str]): The data feed to use.
        adjustment (Optional[str]): The adjustment to apply.

    Returns:
        Dict[str, List[Dict[str, Any]]]: A dictionary of minute bars.
    """
    return bars(
        symbols, timeframe="1Min", limit=limit, feed=feed, adjustment=adjustment
    )


def day_bars(
    symbols: List[str],
    limit: int = 1,
    feed: Optional[str] = None,
    adjustment: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetches day bars for a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.
        limit (int): The number of bars to fetch.
        feed (Optional[str]): The data feed to use.
        adjustment (Optional[str]): The adjustment to apply.

    Returns:
        Dict[str, List[Dict[str, Any]]]: A dictionary of day bars.
    """
    return bars(
        symbols, timeframe="1Day", limit=limit, feed=feed, adjustment=adjustment
    )


def latest_closes(symbols: List[str], feed: Optional[str] = None) -> Dict[str, float]:
    """
    Fetches the latest close price for a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.
        feed (Optional[str]): The data feed to use.

    Returns:
        Dict[str, float]: A dictionary of latest close prices.
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


def latest_trades_from_snapshots(snaps: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """
    Extracts the latest trade price from a dictionary of snapshots.

    Args:
        snaps (Dict[str, Dict[str, Any]]): A dictionary of snapshots.

    Returns:
        Dict[str, float]: A dictionary of latest trade prices.
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
        except Exception:
            continue
    if not out:
        log.warning("no valid latest trade prices extracted from snapshots")
    return out


def has_data(data_map: Optional[Dict[str, Any]]) -> bool:
    """
    Checks if a dictionary of data has any data.

    Args:
        data_map (Optional[Dict[str, Any]]): A dictionary of data.

    Returns:
        bool: True if the dictionary has data, False otherwise.
    """
    if not data_map:
        return False
    for v in data_map.values():
        if v:
            return True
    return False
