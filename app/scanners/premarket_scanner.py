# app/scanners/premarket_scanner.py
from typing import List, Dict, Any
from statistics import mean
from app.config import settings
from app.data.data_client import get_universe, get_daily_bars, get_latest_quote, get_latest_trade

def _gap_pct(today_open: float, prev_close: float) -> float:
    if prev_close <= 0:
        return 0.0
    return (today_open - prev_close) / prev_close * 100.0

def _spread_pct(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2 if (bid and ask) else 0.0
    if mid <= 0:
        return 999.0
    return (ask - bid) / mid * 100.0

def build_premarket_watchlist() -> List[Dict[str, Any]]:
    universe = get_universe(limit=250)
    bars_map = get_daily_bars(universe, limit=6)  # 5-day avg vol + today
    candidates: List[Dict[str, Any]] = []

    for sym in universe:
        bars = bars_map.get(sym, [])
        if len(bars) < 2:
            continue
        # bars are chronological; last is most recent (today pre/early)
        prev = bars[-2]
        today = bars[-1]
        prev_close = prev.get("c", 0.0)
        today_open = today.get("o", 0.0)

        gap = _gap_pct(today_open, prev_close)

        # 5-day avg volume (exclude today)
        vol_hist = [b.get("v", 0) for b in bars[:-1] if b.get("v", 0) is not None]
        avg_vol = mean(vol_hist) if vol_hist else 0
        today_vol = today.get("v", 0)

        rvol = (today_vol / avg_vol) if avg_vol else 0.0

        # latest quote/trade for price/spread
        q = get_latest_quote(sym) or {}
        t = get_latest_trade(sym) or {}
        bid = float(q.get("bp") or 0)
        ask = float(q.get("ap") or 0)
        last = float(t.get("p") or 0)

        price_ok = settings.price_min <= (last or today_open) <= settings.price_max
        gap_ok = gap >= settings.gap_min_pct
        rvol_ok = rvol >= settings.rvol_min
        spread_ok = _spread_pct(bid, ask) <= settings.spread_max_pct_pre

        if price_ok and (gap_ok or rvol_ok) and spread_ok:
            dollar_vol = (last or today_open) * today_vol
            if dollar_vol >= settings.dollar_vol_min_pre:
                candidates.append({
                    "symbol": sym,
                    "last": round(last, 4),
                    "bid": bid, "ask": ask,
                    "spread_pct": round(_spread_pct(bid, ask), 3),
                    "gap_pct": round(gap, 2),
                    "rvol": round(rvol, 2),
                    "dollar_vol": int(dollar_vol)
                })

    # sort by RVOL desc then gap desc
    candidates.sort(key=lambda x: (x["rvol"], x["gap_pct"]), reverse=True)
    return candidates[: settings.max_watchlist]