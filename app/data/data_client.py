from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.dal.helpers import batch_latest_close, batch_latest_volume, fetch_latest_bar
from app.dal.manager import MarketDataDAL
from app.adapters.market.alpaca_provider import day_bars as alpaca_day_bars
from app.adapters.market.alpaca_provider import minute_bars as alpaca_minute_bars

# Providers (external I/O lives here)
from app.adapters.market.alpaca_provider import snapshots as alpaca_snapshots

# Config flags (pure)
from app.utils.env import PRICE_PROVIDERS

# Yahoo enabled flag derived from PRICE_PROVIDERS
YF_ENABLED: bool = any(p.lower() == "yahoo" for p in PRICE_PROVIDERS)

_DAL_SINGLETON: Optional[MarketDataDAL] = None


def _get_dal() -> MarketDataDAL:
    global _DAL_SINGLETON
    if _DAL_SINGLETON is None:
        _DAL_SINGLETON = MarketDataDAL(enable_postgres_metadata=False)
    return _DAL_SINGLETON

def _apply_yahoo_prices(target: Dict[str, Dict[str, Any]], symbols: List[str]) -> None:
    if not symbols:
        return
    if not YF_ENABLED:
        logger.warning(
            "Yahoo provider disabled; cannot fall back for {} symbols", len(symbols)
        )
        return
    dal = _get_dal()
    intr: Dict[str, float] = {}
    source: Dict[str, str] = {}
    for sym in symbols:
        key = sym.strip().upper()
        if not key:
            continue
        bar, vendor = fetch_latest_bar(dal, key, interval="1Min")
        if bar and bar.close and float(bar.close) > 0:
            intr[key] = float(bar.close)
            source[key] = f"dal_{vendor}_1m" if vendor else "dal_1m"

    remaining = [s.strip().upper() for s in symbols if s and s.strip().upper() not in intr]
    close = batch_latest_close(dal, remaining) if remaining else {}

    for sym in symbols:
        key = sym.strip().upper()
        if not key:
            continue
        entry = target.setdefault(
            key, {"last": 0.0, "price_source": "none", "ohlcv": {}}
        )
        if key in intr:
            entry["last"] = intr[key]
            entry["price_source"] = source.get(key, "dal_1m")
            continue
        price = close.get(key)
        if price and float(price) > 0:
            entry["last"] = float(price)
            entry["price_source"] = "dal_yahoo_close"


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
    except Exception as exc:  # nosec B110 - diagnostic only
        logger.debug("midquote calculation failed: {}", exc)
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
            logger.debug("snapshot_to_ohlcv parse error kind={} x={}", kind, x)
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
    except Exception as exc:
        logger.debug("latest_price_with_source trade parse error {}: {}", symbol, exc)

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
        logger.debug("latest_price_with_source 1m error {}: {}", symbol, e)

    # 4) daily bar close (today)
    try:
        d = alpaca_day_bars([symbol], limit=1).get(symbol.upper(), [])
        if d:
            c = d[-1].get("c")
            if c is not None and float(c) > 0:
                return float(c), "daily"
    except Exception as exc:
        logger.debug("latest_price_with_source daily bar error {}: {}", symbol, exc)

    # 5) yahoo fallbacks if enabled
    if YF_ENABLED:
        dal = _get_dal()
        try:
            bar, vendor = fetch_latest_bar(dal, symbol, interval="1Min")
            if bar and bar.close and float(bar.close) > 0:
                source = f"dal_{vendor}_1m" if vendor else "dal_1m"
                return float(bar.close), source
        except Exception as exc:
            logger.debug(
                "latest_price_with_source dal 1m error {}: {}", symbol, exc
            )
        try:
            closes = batch_latest_close(dal, [symbol])
            y_close = closes.get(symbol.upper())
            if y_close and float(y_close) > 0:
                return float(y_close), "dal_yahoo_close"
        except Exception as exc:
            logger.debug(
                "latest_price_with_source dal close error {}: {}", symbol, exc
            )

    return 0.0, "none"


# --------------------------------------------------------------------------------------
# Batch orchestration used by endpoints
# --------------------------------------------------------------------------------------


def batch_latest_ohlcv(
    symbols: List[str], feed: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
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
    :param feed: Optional Alpaca feed hint ("iex" for paper, "sip" for paid).
    """
    syms = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return {}

    snaps = alpaca_snapshots(syms, feed=feed)
    snaps_empty = not snaps or all(not snaps.get(s) for s in syms)
    if snaps_empty:
        logger.warning(
            "alpaca snapshots returned empty payload; falling back to Yahoo for {} symbols",
            len(syms),
        )
    force_yahoo_fallback = snaps_empty
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
    bars_empty = False
    if union_syms:
        bars_map = alpaca_day_bars(union_syms, limit=1, feed=feed)
        bars_empty = not bars_map or all(not bars_map.get(s) for s in union_syms)
        if bars_empty:
            logger.warning(
                "alpaca day bars returned empty payload; falling back to Yahoo for {} symbols",
                len(union_syms),
            )
        force_yahoo_fallback = force_yahoo_fallback or bars_empty
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
                except Exception as exc:
                    logger.debug(
                        "batch_latest_ohlcv: failed to coerce close for {}: {}",
                        sym,
                        exc,
                    )
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
                    except Exception as exc:
                        logger.debug(
                            "batch_latest_ohlcv: volume coercion failed for {}: {}",
                            sym,
                            exc,
                        )
            except Exception as exc:
                logger.debug(
                    "batch_latest_ohlcv: error hydrating OHLCV for {}: {}", sym, exc
                )
            if changed:
                out[sym]["ohlcv"] = ohlcv

    if force_yahoo_fallback:
        _apply_yahoo_prices(out, syms)

    # Third pass: Yahoo fallbacks for any unresolved zeros
    unresolved_price = [s for s, d in out.items() if (d.get("last") or 0) <= 0]
    if YF_ENABLED and unresolved_price:
        dal = _get_dal()
        ok_intr: Dict[str, Tuple[float, str]] = {}
        for sym in unresolved_price:
            bar, vendor = fetch_latest_bar(dal, sym, interval="1Min")
            if bar and bar.close and float(bar.close) > 0:
                source = f"dal_{vendor}_1m" if vendor else "dal_1m"
                ok_intr[sym] = (float(bar.close), source)
        remaining = [s for s in unresolved_price if s not in ok_intr]
        ok_close = batch_latest_close(dal, remaining) if remaining else {}
        for sym in unresolved_price:
            if sym in ok_intr:
                price, src = ok_intr[sym]
                out[sym]["last"] = price
                out[sym]["price_source"] = src
            elif sym in ok_close:
                out[sym]["last"] = float(ok_close[sym])
                out[sym]["price_source"] = "dal_yahoo_close"

    # Fourth pass: Yahoo daily volume for any symbols still showing v==0
    unresolved_vol = [
        s for s, d in out.items() if int((d.get("ohlcv") or {}).get("v", 0)) <= 0
    ]
    if YF_ENABLED and unresolved_vol:
        dal = _get_dal()
        y_vol = batch_latest_volume(dal, unresolved_vol)
        for sym in unresolved_vol:
            vol = y_vol.get(sym)
            if vol and vol > 0:
                ohlcv = out[sym].get("ohlcv") or {}
                ohlcv["v"] = int(vol)
                out[sym]["ohlcv"] = ohlcv

    return out


# --------------------------------------------------------------------------------------
# Data diagnostics helper
# --------------------------------------------------------------------------------------


def data_health(symbols: List[str], feed: Optional[str] = None) -> Dict[str, Any]:
    """
    Lightweight diagnostics for upstream data availability.
    Returns counts and lists of symbols with empty Alpaca snapshots or day bars.
    """
    syms = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return {
            "count": 0,
            "feed": feed or "auto",
            "empty_snapshots": [],
            "empty_day_bars": [],
        }

    snaps = alpaca_snapshots(syms, feed=feed)
    empty_snapshots = [s for s in syms if not snaps.get(s)]

    bars_map = alpaca_day_bars(syms, limit=1, feed=feed)
    empty_day_bars = [s for s in syms if not bars_map.get(s)]

    return {
        "count": len(syms),
        "feed": feed or "auto",
        "empty_snapshots": empty_snapshots,
        "empty_day_bars": empty_day_bars,
    }


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
        logger.debug(
            "get_minutes_bars: non-1Min timeframe requested={}; defaulting to 1Min",
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
