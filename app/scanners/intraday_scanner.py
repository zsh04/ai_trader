from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from app.data.data_client import get_universe
from app.providers.yahoo_provider import (
    get_history_daily,
    intraday_last,
    latest_volume,
)

NY_TZ = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
SESSION_MINUTES = 390


@dataclass
class IntradayParams:
    """
    A data class for intraday scanner parameters.

    Attributes:
        rvol_threshold (float): The relative volume threshold.
        min_price (float): The minimum price.
        min_curr_vol (int): The minimum current volume.
        adv_window (int): The average daily volume window.
        max_symbols (int): The maximum number of symbols to scan.
    """
    rvol_threshold: float = 1.8
    min_price: float = 3.0
    min_curr_vol: int = 250_000
    adv_window: int = 20
    max_symbols: int = 200


def _minutes_since_open(now: Optional[datetime] = None) -> int:
    """
    Calculates the number of minutes since the market opened.

    Args:
        now (Optional[datetime]): The current time.

    Returns:
        int: The number of minutes since the market opened.
    """
    now = now or datetime.now(tz=NY_TZ)
    open_dt = datetime.combine(now.date(), SESSION_OPEN, tzinfo=NY_TZ)
    minutes = int(max(1, min(SESSION_MINUTES, (now - open_dt).total_seconds() // 60)))
    return minutes


def _expected_volume_fraction(now: Optional[datetime] = None) -> float:
    """
    Calculates the expected volume fraction.

    Args:
        now (Optional[datetime]): The current time.

    Returns:
        float: The expected volume fraction.
    """
    return _minutes_since_open(now) / SESSION_MINUTES


def _adv20(symbol: str, window: int) -> Optional[float]:
    """
    Calculates the 20-day average daily volume.

    Args:
        symbol (str): The symbol to calculate the ADV for.
        window (int): The lookback window.

    Returns:
        Optional[float]: The 20-day ADV, or None if not available.
    """
    try:
        start = datetime.now(tz=NY_TZ).date() - timedelta(days=90)
        df = get_history_daily(symbol, start=start.isoformat())
        if df is None or df.empty or "volume" not in df.columns:
            return None
        if df.index[-1].date() == datetime.now(tz=NY_TZ).date():
            df = df.iloc[:-1]
        lookback = df.tail(window)
        if lookback.empty:
            return None
        return float(lookback["volume"].mean())
    except Exception:
        return None


def _tag_reasons(last: float, rvol: Optional[float], adv: Optional[float]) -> List[str]:
    """
    Tags the reasons for a symbol being included in a scan.

    Args:
        last (float): The last price.
        rvol (Optional[float]): The relative volume.
        adv (Optional[float]): The average daily volume.

    Returns:
        List[str]: A list of tags.
    """
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
    Scans for intraday trading opportunities.

    Args:
        symbols (Optional[Iterable[str]]): A list of symbols to scan.
        params (Optional[IntradayParams]): The parameters for the scan.

    Returns:
        List[Dict]: A list of dictionaries, where each dictionary represents a trading opportunity.
    """
    p = params or IntradayParams()

    uni = list(symbols or get_universe())
    if not uni:
        return []
    if len(uni) > p.max_symbols:
        uni = uni[: p.max_symbols]

    last_map: Dict[str, float] = intraday_last(uni)
    vol_map: Dict[str, int] = latest_volume(uni)

    frac = _expected_volume_fraction()
    out: List[Dict] = []

    for sym in uni:
        last = float(last_map.get(sym) or 0.0)
        vol = int(vol_map.get(sym) or 0)

        if last < p.min_price or vol < p.min_curr_vol:
            continue

        adv = _adv20(sym, p.adv_window)
        rvol = None
        if adv and adv > 0 and frac > 0:
            rvol = vol / (adv * frac)

        if rvol is None or rvol < p.rvol_threshold:
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

    out.sort(
        key=lambda d: (float(d.get("rvol") or 0), int(d.get("volume") or 0)),
        reverse=True,
    )
    return out
