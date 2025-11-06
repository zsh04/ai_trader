from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from app.dal.helpers import fetch_latest_bar
from app.dal.manager import MarketDataDAL
from app.data.data_client import get_universe

NY_TZ = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
SESSION_MINUTES = 390  # 6.5 hours

logger = logging.getLogger(__name__)


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


def _adv20(dal: MarketDataDAL, symbol: str, window: int) -> Optional[float]:
    """
    Compute ADV over `window` *previous* sessions (exclude today).
    """
    try:
        start_dt = datetime.now(tz=NY_TZ) - timedelta(days=90)
        batch = dal.fetch_bars(
            symbol,
            start=start_dt.astimezone(UTC),
            end=None,
            interval="1Day",
            vendor="yahoo",
            limit=window + 5,
        )
        rows = batch.bars.data
        if not rows:
            return None
        today = datetime.now(tz=NY_TZ).date()
        volumes: List[float] = []
        for bar in rows:
            bar_date = bar.timestamp.astimezone(NY_TZ).date()
            if bar_date == today:
                continue
            if bar.volume:
                volumes.append(float(bar.volume))
        if len(volumes) < window:
            return None
        return float(sum(volumes[-window:]) / window)
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

    dal = MarketDataDAL(enable_postgres_metadata=False)

    last_map: Dict[str, float] = {}
    vol_map: Dict[str, int] = {}
    source_map: Dict[str, str] = {}

    for sym in uni:
        bar, vendor = fetch_latest_bar(dal, sym, interval="1Min")
        if not bar:
            continue
        last_map[sym] = float(bar.close or 0.0)
        vol_map[sym] = int(bar.volume or 0)
        source_map[sym] = f"{vendor}_1m" if vendor else "unknown"

    frac = _expected_volume_fraction()
    out: List[Dict] = []

    for sym in uni:
        last = float(last_map.get(sym) or 0.0)
        vol = int(vol_map.get(sym) or 0)

        # Quick price/vol guard
        if last < p.min_price or vol < p.min_curr_vol:
            continue

        adv = _adv20(dal, sym, p.adv_window)
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
            "price_source": source_map.get(sym, "unknown"),
        }
        out.append(entry)

    # Sort by rvol desc, then volume desc
    out.sort(
        key=lambda d: (float(d.get("rvol") or 0), int(d.get("volume") or 0)),
        reverse=True,
    )
    return out
