from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.providers.alpaca_provider import (
    day_bars as alpaca_day_bars,
)
from app.providers.alpaca_provider import (
    minute_bars as alpaca_minute_bars,
)

# Providers (all external I/O lives here)
from app.providers.alpaca_provider import (
    snapshots as alpaca_snapshots,
)
from app.providers.yahoo_provider import (
    intraday_last as yf_intraday_last,
)
from app.providers.yahoo_provider import (
    latest_close as yf_latest_close,
)
from app.providers.yahoo_provider import (
    latest_volume as yf_latest_volume,
)

# Config flags (pure)
from app.utils.env import PRICE_PROVIDERS

log = logging.getLogger(__name__)

# Yahoo enabled flag derived from PRICE_PROVIDERS
YF_ENABLED: bool = any(p.lower() == "yahoo" for p in PRICE_PROVIDERS)

# --------------------------------------------------------------------------------------
# Public: domain helpers (pure logic)
# --------------------------------------------------------------------------------------


def _midquote(snap: Dict[str, Any]) -> float:
    q = (snap or {}).get("latestQuote") or {}
    bp = q.get("bp")
    ap = q.get("ap")
    try:
        if bp is not None and ap is not None and float(bp) > 0 and float(ap) > 0:
            return (float(bp) + float(ap)) / 2.0
    except Exception:
        pass
    return 0.0


def snapshot_to_ohlcv(snap: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer today's dailyBar; if empty/zero (premarket/after-hours), fall back to prevDailyBar."""
    dbar = (snap or {}).get("dailyBar") or {}
    pbar = (snap or {}).get("prevDailyBar") or {}
    pick = dbar if (dbar.get("c") not in (None, 0, 0.0)) else pbar

    def _f(x: Any, kind: str) -> float:
        try:
            return float(x or 0.0)
        except Exception:
            log.debug("snapshot_to_ohlcv parse error kind=%s x=%s", kind, x)
            return 0.0

    return {
        "o": _f((pick or {}).get("o"), "o"),
        "h": _f((pick or {}).get("h"), "h"),
        "l": _f((pick or {}).get("l"), "l"),
        "c": _f((pick or {}).get("c"), "c"),
        "v": int((pick or {}).get("v") or 0),
    }


def latest_price_with_source(snap: Dict[str, Any], symbol: str) -> Tuple[float, str]:
    """Same logic as latest_price_from_snapshot but returns (price, source)."""
    # 1) latest trade
    try:
        lt = (snap or {}).get("latestTrade") or {}
        p = lt.get("p")
        if p is not None and float(p) > 0:
            return float(p), "trade"
    except Exception:
        pass

    # 2) midquote
    mid = _midquote(snap)
    if mid > 0:
        return mid, "midquote"

    # 3) last 1m close (Alpaca minute bars)
    try:
        m = alpaca_minute_bars([symbol], limit=1)
        arr = m.get(symbol.upper(), [])
        if arr:
            c = arr[-1].get("c")
            if c is not None and float(c) > 0:
                return float(c), "1m"
    except Exception as e:
        log.debug("latest_price_with_source 1m error %s: %s", symbol, e)

    # 4) daily bar close (today)
    try:
        d = alpaca_day_bars([symbol], limit=1).get(symbol.upper(), [])
        if d:
            c = d[-1].get("c")
            if c is not None and float(c) > 0:
                return float(c), "daily"
    except Exception:
        pass

    # 5) yahoo fallbacks if enabled
    if YF_ENABLED:
        try:
            y = yf_intraday_last([symbol]).get(symbol.upper())
            if y and float(y) > 0:
                return float(y), "yahoo_1m"
        except Exception:
            pass
        try:
            y = yf_latest_close([symbol]).get(symbol.upper())
            if y and float(y) > 0:
                return float(y), "yahoo_close"
        except Exception:
            pass

    return 0.0, "none"


# --------------------------------------------------------------------------------------
# Batch orchestration used by endpoints
# --------------------------------------------------------------------------------------


def batch_latest_ohlcv(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Returns a map:
      {
        "AAPL": {
          "last": 187.34,
          "price_source": "trade|midquote|1m|daily|yahoo_1m|yahoo_close|none",
          "ohlcv": {"o":..., "h":..., "l":..., "c":..., "v":...}
        },
        ...
      }
    """
    syms = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return {}

    snaps = alpaca_snapshots(syms)
    out: Dict[str, Dict[str, Any]] = {}

    needs_price_from_bar: List[str] = []
    needs_vol_from_bar: List[str] = []

    # First pass: from snapshots + immediate fallbacks
    for sym in syms:
        snap = snaps.get(sym) or {}
        last, source = latest_price_with_source(snap, sym)
        ohlcv = snapshot_to_ohlcv(snap)

        if last <= 0:
            needs_price_from_bar.append(sym)
        if int(ohlcv.get("v") or 0) <= 0:
            needs_vol_from_bar.append(sym)

        out[sym] = {"last": last, "price_source": source, "ohlcv": ohlcv}

    # Second pass: hydrate with 1Day bars in one batch (price + volume)
    union_syms = sorted(set(needs_price_from_bar + needs_vol_from_bar))
    if union_syms:
        bars_map = alpaca_day_bars(union_syms, limit=1)
        for sym in union_syms:
            seq = bars_map.get(sym, [])
            if not seq:
                continue
            b = seq[-1]
            # fill price if still zero
            if out[sym]["last"] <= 0:
                try:
                    cval = float(b.get("c") or 0)
                    if cval > 0:
                        out[sym]["last"] = cval
                        out[sym]["price_source"] = "bars_close"
                except Exception:
                    pass
            # hydrate OHLCV fields
            ohlcv = out[sym].get("ohlcv") or {}
            changed = False
            try:
                if float(ohlcv.get("o") or 0) <= 0 and b.get("o") is not None:
                    ohlcv["o"] = float(b.get("o") or 0)
                    changed = True
                if float(ohlcv.get("h") or 0) <= 0 and b.get("h") is not None:
                    ohlcv["h"] = float(b.get("h") or 0)
                    changed = True
                if float(ohlcv.get("l") or 0) <= 0 and b.get("l") is not None:
                    ohlcv["l"] = float(b.get("l") or 0)
                    changed = True
                if float(ohlcv.get("c") or 0) <= 0 and b.get("c") is not None:
                    ohlcv["c"] = float(b.get("c") or 0)
                    changed = True
                if int(ohlcv.get("v") or 0) <= 0 and b.get("v") is not None:
                    try:
                        ohlcv["v"] = int(b.get("v") or 0)
                        changed = True
                    except Exception:
                        pass
            except Exception:
                pass
            if changed:
                out[sym]["ohlcv"] = ohlcv

    # Third pass: Yahoo fallbacks for any unresolved zeros
    unresolved_price = [s for s, d in out.items() if (d.get("last") or 0) <= 0]
    if YF_ENABLED and unresolved_price:
        y_intr = yf_intraday_last(unresolved_price)
        remaining = [s for s in unresolved_price if s not in y_intr]
        y_close = yf_latest_close(remaining) if remaining else {}
        for sym in unresolved_price:
            if sym in y_intr and y_intr[sym] > 0:
                out[sym]["last"] = y_intr[sym]
                out[sym]["price_source"] = "yahoo_1m"
            elif sym in y_close and y_close[sym] > 0:
                out[sym]["last"] = y_close[sym]
                out[sym]["price_source"] = "yahoo_close"

    # Fourth pass: Yahoo daily volume for any symbols still showing v==0
    unresolved_vol = [
        s for s, d in out.items() if int((d.get("ohlcv") or {}).get("v", 0)) <= 0
    ]
    if YF_ENABLED and unresolved_vol:
        y_vol = yf_latest_volume(unresolved_vol)
        for sym in unresolved_vol:
            vol = y_vol.get(sym)
            if vol and vol > 0:
                ohlcv = out[sym].get("ohlcv") or {}
                ohlcv["v"] = int(vol)
                out[sym]["ohlcv"] = ohlcv

    return out


# --------------------------------------------------------------------------------------
# Backward-compat convenience for callers during migration
# --------------------------------------------------------------------------------------


def get_universe() -> List[str]:
    """Default scanning universe; overridable via WATCHLIST_UNIVERSE env in higher layer."""
    # To avoid env coupling here, return a sensible static universe.
    return [
        "SPY",
        "QQQ",
        "IWM",
        "AAPL",
        "MSFT",
        "NVDA",
        "TSLA",
        "META",
        "AMZN",
        "GOOGL",
        "SHOP",
        "NFLX",
        "AMD",
        "INTC",
        "SMCI",
        "PLTR",
        "SOFI",
        "MARA",
        "RIOT",
        "SOUN",
    ]


# Thin proxies so existing imports keep working while we migrate call sites.


def get_snapshots_batch(
    symbols: List[str], feed: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    return alpaca_snapshots(symbols, feed=feed)


def get_minutes_bars(
    symbols: List[str],
    timeframe: str = "1Min",
    limit: int = 1,
    feed: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    # Only 1Min supported by the provider helper; keep timeframe param for legacy signature
    if timeframe not in ("1Min", "1min", "1MIN"):
        log.debug(
            "get_minutes_bars: non-1Min timeframe requested=%s; defaulting to 1Min",
            timeframe,
        )
    return alpaca_minute_bars(symbols, limit=limit, feed=feed)


def get_daily_bars(
    symbols: List[str], limit: int = 1, feed: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    return alpaca_day_bars(symbols, limit=limit, feed=feed)


def get_minute_bars(
    symbols: List[str], limit: int = 1, feed: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    # legacy alias
    return get_minutes_bars(symbols, timeframe="1Min", limit=limit, feed=feed)
