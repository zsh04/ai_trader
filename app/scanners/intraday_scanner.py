from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from app.data.data_client import get_universe
from app.providers.yahoo_provider import (
    get_history_daily,  # daily history for ADV computation
    intraday_last,
    latest_volume,
)

NY_TZ = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
SESSION_MINUTES = 390  # 6.5 hours


@dataclass
class IntradayParams:
    rvol_threshold: float = 1.8
    min_price: float = 3.0
    min_curr_vol: int = 250_000
    adv_window: int = 20
    max_symbols: int = 200  # cap universe for speed


def _minutes_since_open(now: Optional[datetime] = None) -> int:
    """
    Minutes since regular session open (NYSE) clamped to [1, 390].
    """
    now = now or datetime.now(tz=NY_TZ)
    open_dt = datetime.combine(now.date(), SESSION_OPEN, tzinfo=NY_TZ)
    minutes = int(max(1, min(SESSION_MINUTES, (now - open_dt).total_seconds() // 60)))
    return minutes


def _expected_volume_fraction(now: Optional[datetime] = None) -> float:
    """
    Rough linear fraction of the day that has elapsed (regular session only).
    """
    return _minutes_since_open(now) / SESSION_MINUTES


def _adv20(symbol: str, window: int) -> Optional[float]:
    """
    Compute ADV over `window` *previous* sessions (exclude today).
    """
    try:
        # 60 trading days back is plenty to cover a 20d lookback
        start = datetime.now(tz=NY_TZ).date() - timedelta(days=90)
        df = get_history_daily(symbol, start=start.isoformat())
        if df is None or df.empty or "volume" not in df.columns:
            return None
        # Drop the last row if it's today (sometimes yfinance includes partial)
        if df.index[-1].date() == datetime.now(tz=NY_TZ).date():
            df = df.iloc[:-1]
        lookback = df.tail(window)
        if lookback.empty:
            return None
        return float(lookback["volume"].mean())
    except Exception:
        return None


def _tag_reasons(last: float, rvol: Optional[float], adv: Optional[float]) -> List[str]:
    tags: List[str] = []
    if rvol is not None:
        if rvol >= 3:
            tags.append("🔥 rVOL≥3")
        elif rvol >= 2:
            tags.append("⬆️ rVOL≥2")
        elif rvol >= 1.5:
            tags.append("rVOL≥1.5")
    if adv and adv > 5_000_000:
        tags.append("liquid")
    if last >= 20:
        tags.append("$20+")
    return tags


def scan_intraday(
    symbols: Optional[Iterable[str]] = None,
    *,
    params: Optional[IntradayParams] = None,
) -> List[Dict]:
    """
    Intraday scanner to detect RVOL spikes / range expansions using Yahoo Finance data.

    Heuristics:
      - Compute current rVOL ≈ current_volume / (ADV20 * elapsed_fraction)
      - Filter by price and liquidity thresholds
      - Return compact dicts suitable for watchlist/notifications

    Notes:
      - Uses batched calls for current last and volume.
      - ADV20 is computed per symbol (one by one); cap the universe for speed.
    """
    p = params or IntradayParams()

    # Universe
    uni = list(symbols or get_universe())
    if not uni:
        return []
    if len(uni) > p.max_symbols:
        uni = uni[: p.max_symbols]

    # Current price and volume (batched)
    last_map: Dict[str, float] = intraday_last(uni)
    vol_map: Dict[str, int] = latest_volume(uni)

    frac = _expected_volume_fraction()
    out: List[Dict] = []

    for sym in uni:
        last = float(last_map.get(sym) or 0.0)
        vol = int(vol_map.get(sym) or 0)

        # Quick price/vol guard
        if last < p.min_price or vol < p.min_curr_vol:
            continue

        adv = _adv20(sym, p.adv_window)
        rvol = None
        if adv and adv > 0 and frac > 0:
            rvol = vol / (adv * frac)

        if rvol is None or rvol < p.rvol_threshold:
            # Still allow through if volume is exceptionally high (e.g., news)
            if vol < max(2 * p.min_curr_vol, (adv or 0) * 0.25):
                continue

        entry = {
            "symbol": sym,
            "last": last,
            "volume": vol,
            "adv20": adv,
            "rvol": rvol,
            "elapsed_frac": round(frac, 3),
            "reasons": _tag_reasons(last, rvol, adv),
            "price_source": "yahoo_1m",
        }
        out.append(entry)

    # Sort by rvol desc, then volume desc
    out.sort(
        key=lambda d: (float(d.get("rvol") or 0), int(d.get("volume") or 0)),
        reverse=True,
    )
    return out
