from app.providers.alpaca_provider import snapshots as get_snapshots_batch, day_bars as get_daily_bars, minute_bars as get_minutes_bars
from app.providers.yahoo_provider import intraday_last as yf_intraday_last, latest_close as yf_latest_close, latest_volume as yf_latest_volume
from app.data.data_client import batch_latest_ohlcv
from app.core.timeutils import now_utc, session_for

def _gap_pct(today_open: float, prev_close: float) -> float:
    if not prev_close or prev_close <= 0:
        return 0.0
    return (today_open - prev_close) / prev_close * 100.0

def _spread_pct(bid: float, ask: float) -> float:
    if not bid or not ask:
        return 999.0
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 999.0
    return (ask - bid) / mid * 100.0

def _pick_price(latest_trade: dict | None, daily_bar: dict | None, prev_daily: dict | None) -> float:
    """
    Use latestTrade price if present; fallback to today's open or prev close.
    """
    if latest_trade and latest_trade.get("p"):
        return float(latest_trade["p"])
    if daily_bar and daily_bar.get("o"):
        return float(daily_bar["o"])
    if prev_daily and prev_daily.get("c"):
        return float(prev_daily["c"])
    return 0.0

def _volumes_for_rvol(bars: List[dict], daily_bar: dict | None) -> Tuple[float, float]:
    """
    Return (today_volume, avg_5d_volume). If today's volume is 0 premarket, we still return 0.
    """
    hist = [b.get("v", 0) for b in bars[:-1] if b.get("v")]
    avg5 = mean(hist[-5:]) if hist else 0.0
    today = float(daily_bar.get("v", 0.0)) if daily_bar else 0.0
    return today, avg5

def build_watchlist(symbols=None, include_filters=True, passthrough=False, include_ohlcv=True):
    """
    Unified watchlist creator:
      - symbols provided => manual mode
      - symbols None/[]  => scanning mode (apply filters if include_filters)
    Session-aware enrichment via batch_latest_ohlcv.
    """
    # 1) pick candidate symbols
    if symbols:
        candidates = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    else:
        candidates = scan_candidates()  # your existing filter logic

    # 2) (optional) apply filters even in manual mode if you want
    if include_filters:
        candidates = apply_filters(candidates)  # existing logic

    # 3) enrich
    snap = batch_latest_ohlcv(candidates)

    # 4) structure response
    items = []
    for sym in candidates:
        d = snap.get(sym, {"last": 0.0, "price_source": "none", "ohlcv": {}})
        items.append({
            "symbol": sym,
            "last": d.get("last", 0.0),
            "price_source": d.get("price_source", "none"),
            "ohlcv": d.get("ohlcv", {}),
        })

    return {
        "session": session_for(now_utc()),
        "asof_utc": now_utc().isoformat(),
        "count": len(items),
        "items": items,
    }