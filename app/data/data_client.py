from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.adapters.notifiers.telegram import TelegramClient
from app.providers.alpaca_provider import day_bars as alpaca_day_bars
from app.providers.alpaca_provider import minute_bars as alpaca_minute_bars
# Providers (all external I/O lives here)
from app.providers.alpaca_provider import snapshots as alpaca_snapshots
from app.providers.yahoo_provider import intraday_last as yf_intraday_last
from app.providers.yahoo_provider import latest_close as yf_latest_close
from app.providers.yahoo_provider import latest_volume as yf_latest_volume
# Config flags (pure)
from app.utils import env as ENV
from app.utils.env import PRICE_PROVIDERS

# Yahoo enabled flag derived from PRICE_PROVIDERS
YF_ENABLED: bool = any(p.lower() == "yahoo" for p in PRICE_PROVIDERS)

_PROVIDER_GAP_STREAK: Dict[str, int] = {"snapshots": 0, "bars": 0}
_ALERT_CLIENT: Optional[TelegramClient] = None


def _send_gap_alert(kind: str, symbol_count: int) -> None:
    token = getattr(ENV, "TELEGRAM_BOT_TOKEN", "") or ""
    chat = getattr(ENV, "TELEGRAM_DEFAULT_CHAT_ID", "") or ""
    if not token or not chat:
        return
    global _ALERT_CLIENT
    if _ALERT_CLIENT is None:
        try:
            _ALERT_CLIENT = TelegramClient(bot_token=token)
        except Exception as exc:
            logger.debug("Failed to initialize TelegramClient for alerts: {}", exc)
            return
    try:
        _ALERT_CLIENT.send_text(
            chat,
            f"⚠️ Alpaca {kind} feed empty twice consecutively for {symbol_count} symbols.",
        )
    except Exception as exc:
        logger.debug("Telegram alert send failed: {}", exc)


def _record_provider_gap(kind: str, is_empty: bool, symbol_count: int) -> None:
    if kind not in _PROVIDER_GAP_STREAK:
        _PROVIDER_GAP_STREAK[kind] = 0
    if not is_empty:
        _PROVIDER_GAP_STREAK[kind] = 0
        return
    _PROVIDER_GAP_STREAK[kind] += 1
    if _PROVIDER_GAP_STREAK[kind] >= 2:
        _send_gap_alert(kind, symbol_count)
        _PROVIDER_GAP_STREAK[kind] = 0


def _apply_yahoo_prices(target: Dict[str, Dict[str, Any]], symbols: List[str]) -> None:
    if not symbols:
        return
    if not YF_ENABLED:
        logger.warning(
            "Yahoo provider disabled; cannot fall back for {} symbols", len(symbols)
        )
        return
    try:
        intr = yf_intraday_last(symbols) or {}
    except Exception as exc:
        logger.debug("Yahoo intraday fallback failed: {}", exc)
        intr = {}
    remaining = [s for s in symbols if s not in intr]
    try:
        close = yf_latest_close(remaining) if remaining else {}
    except Exception as exc:
        logger.debug("Yahoo close fallback failed: {}", exc)
        close = {}

    for sym in symbols:
        entry = target.setdefault(
            sym, {"last": 0.0, "price_source": "none", "ohlcv": {}}
        )
        price = intr.get(sym)
        source = "yahoo_1m"
        if price is None:
            price = close.get(sym)
            source = "yahoo_close"
        if price and float(price) > 0:
            entry["last"] = float(price)
            entry["price_source"] = source


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
        logger.debug("latest_price_with_source 1m error {}: {}", symbol, e)

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
    _record_provider_gap("snapshots", snaps_empty, len(syms))
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
        _record_provider_gap("bars", bars_empty, len(union_syms))
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

    else:
        _record_provider_gap("bars", False, 0)

    if force_yahoo_fallback:
        _apply_yahoo_prices(out, syms)

    # Third pass: Yahoo fallbacks for any unresolved zeros
    unresolved_price = [s for s, d in out.items() if (d.get("last") or 0) <= 0]
    if YF_ENABLED and unresolved_price:
        y_intr_all = yf_intraday_last(unresolved_price)
        ok_intr = {
            s: v for s, v in (y_intr_all or {}).items() if v and float(v) > 0
        }
        remaining = [s for s in unresolved_price if s not in ok_intr]
        y_close_all = yf_latest_close(remaining) if remaining else {}
        ok_close = {
            s: v for s, v in (y_close_all or {}).items() if v and float(v) > 0
        }
        for sym in unresolved_price:
            if sym in ok_intr:
                out[sym]["last"] = float(ok_intr[sym])
                out[sym]["price_source"] = "yahoo_1m"
            elif sym in ok_close:
                out[sym]["last"] = float(ok_close[sym])
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
# Data diagnostics helper
# --------------------------------------------------------------------------------------


def data_health(
    symbols: List[str], feed: Optional[str] = None
) -> Dict[str, Any]:
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
