"""Trading calendar utilities (US equities by default).

This module is timezone-aware and holiday-aware when `pandas_market_calendars`
(`pmc`) is installed. If it's not available, it falls back to a simple
Mon–Fri weekday check.

Primary market keys: XNYS (NYSE) and XNAS (NASDAQ). You can pass other market codes supported by pmc.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

try:  # optional dependency
    import pandas as pd  # type: ignore
    import pandas_market_calendars as mcal  # type: ignore
except Exception:  # pragma: no cover - optional path
    pd = None
    mcal = None

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

# Defaults
DEFAULT_MARKETS = ["XNYS", "XNAS"]
DEFAULT_MARKET = DEFAULT_MARKETS[0]
LOCAL_TZ = "America/Los_Angeles"


# ----------------------------- helpers ---------------------------------


def _tz(tz: Optional[str]) -> dt.tzinfo:
    if tz and ZoneInfo:
        return ZoneInfo(tz)
    # Fallback to UTC if zoneinfo not present
    return dt.timezone.utc


@lru_cache(maxsize=8)
def _calendar(market: str = DEFAULT_MARKET):
    if mcal is None:
        return None
    return mcal.get_calendar(market)


def _to_date(x: dt.date | dt.datetime | str) -> dt.date:
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    # string
    return dt.date.fromisoformat(x)


def _today_local() -> dt.date:
    tz = _tz(LOCAL_TZ)
    now = dt.datetime.now(tz)
    return now.date()


# ------------------------------ API ------------------------------------


def is_trading_day(
    x: dt.date | dt.datetime | str, market: str = DEFAULT_MARKET
) -> bool:
    """Return True if *x* is a trading day for *market*.

    Uses `pandas_market_calendars` when available, otherwise falls back to
    a simple Mon–Fri check.

    Supports markets: XNYS, XNAS by default.
    """
    d = _to_date(x)
    cal = _calendar(market)
    if cal is None:
        # Fallback: Monday–Friday only (no holiday awareness)
        return d.weekday() < 5
    # pmc path
    valid = cal.valid_days(start_date=d, end_date=d)
    return len(valid) > 0


def next_trading_day(
    x: dt.date | dt.datetime | str, market: str = DEFAULT_MARKET
) -> dt.date:
    """Return the next trading day on/after *x* (strictly after if *x* is trading).

    Supports markets: XNYS, XNAS by default.
    """
    d = _to_date(x)
    cal = _calendar(market)
    if cal is None:
        # Fallback: iterate Mon–Fri
        d2 = d + dt.timedelta(days=1)
        while d2.weekday() >= 5:
            d2 += dt.timedelta(days=1)
        return d2
    days = cal.valid_days(start_date=d, end_date=d + dt.timedelta(days=10))
    # `valid_days` returns business days; if d is trading day, first element is d
    if len(days) == 0:
        return d
    if pd is not None and isinstance(days, pd.DatetimeIndex) and days[0].date() == d:
        return days[1].date() if len(days) > 1 else d
    return days[0].date()


def previous_trading_day(
    x: dt.date | dt.datetime | str, market: str = DEFAULT_MARKET
) -> dt.date:
    """Return the previous trading day before *x*.

    Supports markets: XNYS, XNAS by default.
    """
    d = _to_date(x)
    cal = _calendar(market)
    if cal is None:
        d2 = d - dt.timedelta(days=1)
        while d2.weekday() >= 5:
            d2 -= dt.timedelta(days=1)
        return d2
    days = cal.valid_days(start_date=d - dt.timedelta(days=10), end_date=d)
    if len(days) == 0:
        return d
    # last valid day strictly before d
    if pd is not None and isinstance(days, pd.DatetimeIndex) and days[-1].date() == d:
        return days[-2].date() if len(days) > 1 else d
    return days[-1].date()


@dataclass(frozen=True)
class MarketHours:
    market_open: dt.datetime
    market_close: dt.datetime


def market_hours(
    x: dt.date | dt.datetime | str, market: str = DEFAULT_MARKET, tz: str = LOCAL_TZ
) -> Optional[MarketHours]:
    """Return local-market open/close datetimes for *x*.

    If pmc is not installed, returns None.

    Supports markets: XNYS, XNAS by default.
    """
    d = _to_date(x)
    cal = _calendar(market)
    if cal is None or pd is None:
        return None
    sched = cal.schedule(start_date=d, end_date=d)
    if sched.empty:
        return None
    row = sched.iloc[0]
    # pmc returns tz-aware timestamps in UTC by default; convert to requested tz
    tzinfo = _tz(tz)
    op = row["market_open"].to_pydatetime().astimezone(tzinfo)
    cl = row["market_close"].to_pydatetime().astimezone(tzinfo)
    return MarketHours(market_open=op, market_close=cl)


def is_market_open(
    ts: Optional[dt.datetime] = None, market: str = DEFAULT_MARKET, tz: str = LOCAL_TZ
) -> bool:
    """Return True if the market is open at *ts* (defaults to now in local time).

    Supports markets: XNYS, XNAS by default.
    """
    tzinfo = _tz(tz)
    ts = (
        ts.astimezone(tzinfo)
        if isinstance(ts, dt.datetime)
        else dt.datetime.now(tzinfo)
    )
    hours = market_hours(ts.date(), market=market, tz=tz)
    if hours is None:
        # Fallback: between 9:30 and 16:00 local time on weekdays
        if ts.weekday() >= 5:
            return False
        open_time = ts.replace(hour=9, minute=30, second=0, microsecond=0)
        close_time = ts.replace(hour=16, minute=0, second=0, microsecond=0)
        return open_time <= ts <= close_time
    return hours.market_open <= ts <= hours.market_close


__all__ = [
    "DEFAULT_MARKET",
    "DEFAULT_MARKETS",
    "is_trading_day",
    "next_trading_day",
    "previous_trading_day",
    "market_hours",
    "is_market_open",
    "MarketHours",
]
