# app/scanners/premarket_scanner.py
from typing import List, Dict, Any, Tuple, Optional
from statistics import mean
from app.config import settings
from app.data.data_client import get_universe, get_daily_bars, get_snapshots_batch

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

def build_premarket_watchlist(debug: bool = False, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    universe = [s.strip().upper() for s in symbols] if symbols else get_universe(limit=400)
    bars_map = get_daily_bars(universe, limit=7)  # includes prev days + today
    snaps = get_snapshots_batch(universe)

    cands: List[Dict[str, Any]] = []
    reasons_dropped: Dict[str, str] = {}

    for sym in universe:
        snap = snaps.get(sym) or {}
        lt = snap.get("latestTrade")
        lq = snap.get("latestQuote")
        dbar = snap.get("dailyBar")       # today so far
        pbar = snap.get("prevDailyBar")   # yesterday

        bars = bars_map.get(sym, [])
        if len(bars) < 2 or not pbar:
            reasons_dropped[sym] = "insufficient_history"
            continue

        prev_close = float(pbar.get("c", 0.0))
        today_open = float(dbar.get("o", 0.0)) if dbar else 0.0
        price_now  = _pick_price(lt, dbar, pbar)

        # core metrics
        gap = _gap_pct(today_open or price_now, prev_close)

        bid = float(lq.get("bp", 0.0)) if lq else 0.0
        ask = float(lq.get("ap", 0.0)) if lq else 0.0
        spread = _spread_pct(bid, ask)

        today_vol, avg5 = _volumes_for_rvol(bars, dbar)
        rvol = (today_vol / avg5) if avg5 else 0.0

        # price band
        price_ok = settings.price_min <= price_now <= settings.price_max

        # relaxed premarket logic:
        # - pass if EITHER (gap >= threshold) OR (rvol >= threshold), AND spread is reasonable
        # - compute dollar volume with best available info
        gap_ok = gap >= settings.gap_min_pct
        rvol_ok = rvol >= settings.rvol_min
        spread_ok = spread <= settings.spread_max_pct_pre

        # dollar volume proxy: if today_vol is 0 premarket, fall back to avg5 * price_now * a small factor
        if today_vol > 0:
            dollar_vol = price_now * today_vol
        else:
            dollar_vol = price_now * avg5 * 0.05  # assume 5% of avg volume traded premarket (rough heuristic)

        dollar_ok = dollar_vol >= float(settings.dollar_vol_min_pre)

        if price_ok and spread_ok and (gap_ok or rvol_ok) and dollar_ok:
            cands.append({
                "symbol": sym,
                "price": round(price_now, 4),
                "bid": bid, "ask": ask,
                "spread_pct": round(spread, 3),
                "gap_pct": round(gap, 2),
                "rvol": round(rvol, 2),
                "dollar_vol_est": int(dollar_vol),
            })
        else:
            if debug:
                reasons = []
                if not price_ok:  reasons.append("price")
                if not spread_ok: reasons.append("spread")
                if not (gap_ok or rvol_ok): reasons.append("gap/rvol")
                if not dollar_ok: reasons.append("dvol")
                reasons_dropped[sym] = ",".join(reasons) or "unknown"

    # rank: prioritize rvol, then gap, then tighter spread
    cands.sort(key=lambda x: (x["rvol"], x["gap_pct"], -x["spread_pct"]), reverse=True)
    return cands[: settings.max_watchlist]