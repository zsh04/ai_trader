from __future__ import annotations

import logging
from statistics import mean
from typing import Iterable, List, Optional

from app.core.timeutils import now_utc, session_for
from app.data.data_client import batch_latest_ohlcv, get_universe
from app.utils.env import MAX_WATCHLIST

log = logging.getLogger(__name__)

FALLBACK_WATCHLIST_CAP = 15
INVALID_SPREAD_PCT = 999.0
PCT_SCALE = 100.0
RVOL_LOOKBACK_DAYS = 5
FINVIZ_MAX_SYMBOLS = 100

DEFAULT_CAP = (
    MAX_WATCHLIST
    if isinstance(MAX_WATCHLIST, int) and MAX_WATCHLIST > 0
    else FALLBACK_WATCHLIST_CAP
)


def _cap_list(syms: list[str], n: int | None) -> list[str]:
    """
    Caps a list of symbols to a given size.

    Args:
        syms (list[str]): A list of symbols.
        n (int | None): The maximum number of symbols to return.

    Returns:
        list[str]: A capped list of symbols.
    """
    if not syms:
        return []
    if n is None or n <= 0:
        return syms[:DEFAULT_CAP]
    return syms[:n]


try:
    from app.sources import dedupe_merge
except Exception:

    def dedupe_merge(*groups: Iterable[str], limit: int | None = None) -> list[str]:
        """
        Deduplicates and merges multiple groups of symbols.

        Args:
            *groups (Iterable[str]): A list of groups of symbols.
            limit (int | None): The maximum number of symbols to return.

        Returns:
            list[str]: A deduplicated and merged list of symbols.
        """
        seen: set[str] = set()
        out: list[str] = []
        for g in groups:
            for s in g or []:
                u = str(s).strip().upper()
                if not u or u in seen:
                    continue
                seen.add(u)
                out.append(u)
                if limit and len(out) >= limit:
                    return out
        return out


try:
    from app.sources.finviz_source import fetch_symbols as finviz_fetch
except Exception:

    def finviz_fetch(*args, **kwargs):
        """
        A fallback for the finviz_fetch function.
        """
        return []


def _gap_pct(today_open: float, prev_close: float) -> float:
    """
    Calculates the gap percentage between today's open and the previous day's close.

    Args:
        today_open (float): Today's open price.
        prev_close (float): The previous day's close price.

    Returns:
        float: The gap percentage.
    """
    if not prev_close or prev_close <= 0:
        return 0.0
    return (today_open - prev_close) / prev_close * PCT_SCALE


def _spread_pct(bid: float, ask: float) -> float:
    """
    Calculates the bid-ask spread percentage.

    Args:
        bid (float): The bid price.
        ask (float): The ask price.

    Returns:
        float: The spread percentage.
    """
    if not bid or not ask:
        return INVALID_SPREAD_PCT
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return INVALID_SPREAD_PCT
    return (ask - bid) / mid * PCT_SCALE


def _pick_price(
    latest_trade: dict | None, daily_bar: dict | None, prev_daily: dict | None
) -> float:
    """
    Picks the most relevant price from a set of sources.

    Args:
        latest_trade (dict | None): The latest trade data.
        daily_bar (dict | None): The daily bar data.
        prev_daily (dict | None): The previous day's daily bar data.

    Returns:
        float: The picked price.
    """
    try:
        if latest_trade and latest_trade.get("p"):
            p = float(latest_trade["p"])
            if p > 0:
                return p
    except Exception:
        pass
    try:
        if daily_bar and daily_bar.get("o"):
            o = float(daily_bar["o"])
            if o > 0:
                return o
    except Exception:
        pass
    try:
        if prev_daily and prev_daily.get("c"):
            c = float(prev_daily["c"])
            if c > 0:
                return c
    except Exception:
        pass
    return 0.0


def _volumes_for_rvol(bars: list[dict], daily_bar: dict | None) -> tuple[float, float]:
    """
    Calculates the volumes for relative volume calculation.

    Args:
        bars (list[dict]): A list of historical bars.
        daily_bar (dict | None): The current daily bar.

    Returns:
        tuple[float, float]: A tuple of (today's volume, average 5-day volume).
    """
    hist = [b.get("v", 0) for b in (bars or []) if b.get("v")]
    avg5 = float(mean(hist[-RVOL_LOOKBACK_DAYS:])) if hist else 0.0
    today = float((daily_bar or {}).get("v") or 0.0)
    return today, avg5


def build_watchlist(
    symbols: list[str] | None = None,
    include_filters: bool = True,
    passthrough: bool = False,
    include_ohlcv: bool = True,
    *,
    include_finviz: bool = False,
    finviz_preset: Optional[str] = None,
    finviz_filters: Optional[list[str]] = None,
    limit: Optional[int] = None,
) -> dict:
    """
    Builds a watchlist.

    Args:
        symbols (list[str] | None): A list of symbols to include in the watchlist.
        include_filters (bool): Whether to apply filters to the watchlist.
        passthrough (bool): Whether to passthrough the symbols without enrichment.
        include_ohlcv (bool): Whether to include OHLCV data in the watchlist.
        include_finviz (bool): Whether to include symbols from Finviz.
        finviz_preset (Optional[str]): The Finviz preset to use.
        finviz_filters (Optional[list[str]]): A list of Finviz filters to use.
        limit (Optional[int]): The maximum number of symbols to include in the watchlist.

    Returns:
        dict: A dictionary representing the watchlist.
    """
    _ts = now_utc()
    _session = session_for(_ts)

    hard_cap = limit if (isinstance(limit, int) and limit > 0) else DEFAULT_CAP

    manual = sorted({s.strip().upper() for s in (symbols or []) if s and s.strip()})
    scanner_default = [] if manual else scan_candidates()

    finviz_list: list[str] = []
    if include_finviz:
        try:
            finviz_list = (
                finviz_fetch(
                    preset=finviz_preset or "Top Gainers",
                    filters=finviz_filters or [],
                    max_symbols=FINVIZ_MAX_SYMBOLS,
                )
                or []
            )
        except Exception as e:
            log.warning("finviz fetch failed: %s", e)
            finviz_list = []

    log.debug(
        (
            "watchlist sources: manual=%d scanner=%d finviz=%d "
            "include_filters=%s limit=%s"
        ),
        len(manual),
        len(scanner_default),
        len(finviz_list),
        include_filters,
        hard_cap,
    )

    candidates = dedupe_merge(manual, scanner_default, finviz_list)
    candidates = sorted(candidates)
    candidates = _cap_list(candidates, hard_cap)

    if not candidates:
        log.info("watchlist: no candidates after merge; returning empty payload")
        return {
            "session": _session,
            "asof_utc": _ts.isoformat(),
            "count": 0,
            "items": [],
        }

    if include_filters:
        candidates = apply_filters(candidates, limit=hard_cap)

    log.debug("watchlist candidates (post-filters): %d", len(candidates))

    snap = batch_latest_ohlcv(candidates)

    if not isinstance(snap, dict):
        log.warning("batch_latest_ohlcv returned non-dict type: %s", type(snap))
        snap = {}

    items: list[dict] = []
    for sym in candidates:
        d = snap.get(sym, {"last": 0.0, "price_source": "none", "ohlcv": {}})
        items.append(
            {
                "symbol": sym,
                "last": float(d.get("last", 0.0) or 0.0),
                "price_source": d.get("price_source", "none"),
                "ohlcv": d.get("ohlcv", {}),
            }
        )

    log.info("watchlist built: %d items", len(items))

    items.sort(key=lambda x: x.get("symbol", ""))

    return {
        "session": _session,
        "asof_utc": _ts.isoformat(),
        "count": len(items),
        "items": items,
    }


def scan_candidates() -> List[str]:
    """
    Scans for candidate symbols.

    Returns:
        List[str]: A list of candidate symbols.
    """
    return get_universe()


def apply_filters(symbols: List[str], limit: Optional[int] = None) -> List[str]:
    """
    Applies filters to a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.
        limit (Optional[int]): The maximum number of symbols to return.

    Returns:
        List[str]: A filtered list of symbols.
    """
    syms = [s.strip().upper() for s in symbols if s and s.strip()]
    cap = limit if isinstance(limit, int) and limit > 0 else DEFAULT_CAP
    return _cap_list(syms, cap)
