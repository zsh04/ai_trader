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

try:
    import pandas as pd
    import pandas_market_calendars as mcal
except Exception:
    pd = None
    mcal = None

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

DEFAULT_MARKETS = ["XNYS", "XNAS"]
DEFAULT_MARKET = DEFAULT_MARKETS[0]
LOCAL_TZ = "America/Los_Angeles"


def _tz(tz: Optional[str]) -> dt.tzinfo:
    """
    Returns a timezone object.

    Args:
        tz (Optional[str]): The timezone string.

    Returns:
        dt.tzinfo: A timezone object.
    """
    if tz and ZoneInfo:
        return ZoneInfo(tz)
    return dt.timezone.utc


@lru_cache(maxsize=8)
def _calendar(market: str = DEFAULT_MARKET):
    """
    Returns a market calendar.

    Args:
        market (str): The market to get the calendar for.

    Returns:
        A market calendar object.
    """
    if mcal is None:
        return None
    return mcal.get_calendar(market)


def _to_date(x: dt.date | dt.datetime | str) -> dt.date:
    """
    Converts a value to a date.

    Args:
        x (dt.date | dt.datetime | str): The value to convert.

    Returns:
        dt.date: A date object.
    """
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(x)


def _today_local() -> dt.date:
    """
    Returns the current date in the local timezone.

    Returns:
        dt.date: The current date.
    """
    tz = _tz(LOCAL_TZ)
    now = dt.datetime.now(tz)
    return now.date()


def is_trading_day(
    x: dt.date | dt.datetime | str, market: str = DEFAULT_MARKET
) -> bool:
    """
    Checks if a given date is a trading day.

    Args:
        x (dt.date | dt.datetime | str): The date to check.
        market (str): The market to check against.

    Returns:
        bool: True if the date is a trading day, False otherwise.
    """
    d = _to_date(x)
    cal = _calendar(market)
    if cal is None:
        return d.weekday() < 5
    valid = cal.valid_days(start_date=d, end_date=d)
    return len(valid) > 0


def next_trading_day(
    x: dt.date | dt.datetime | str, market: str = DEFAULT_MARKET
) -> dt.date:
    """
    Returns the next trading day.

    Args:
        x (dt.date | dt.datetime | str): The date to start from.
        market (str): The market to check against.

    Returns:
        dt.date: The next trading day.
    """
    d = _to_date(x)
    cal = _calendar(market)
    if cal is None:
        d2 = d + dt.timedelta(days=1)
        while d2.weekday() >= 5:
            d2 += dt.timedelta(days=1)
        return d2
    days = cal.valid_days(start_date=d, end_date=d + dt.timedelta(days=10))
    if len(days) == 0:
        return d
    if pd is not None and isinstance(days, pd.DatetimeIndex) and days[0].date() == d:
        return days[1].date() if len(days) > 1 else d
    return days[0].date()


def previous_trading_day(
    x: dt.date | dt.datetime | str, market: str = DEFAULT_MARKET
) -> dt.date:
    """
    Returns the previous trading day.

    Args:
        x (dt.date | dt.datetime | str): The date to start from.
        market (str): The market to check against.

    Returns:
        dt.date: The previous trading day.
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
    if pd is not None and isinstance(days, pd.DatetimeIndex) and days[-1].date() == d:
        return days[-2].date() if len(days) > 1 else d
    return days[-1].date()


@dataclass(frozen=True)
class MarketHours:
    """
    A data class for market hours.

    Attributes:
        market_open (dt.datetime): The market open time.
        market_close (dt.datetime): The market close time.
    """
    market_open: dt.datetime
    market_close: dt.datetime


def market_hours(
    x: dt.date | dt.datetime | str, market: str = DEFAULT_MARKET, tz: str = LOCAL_TZ
) -> Optional[MarketHours]:
    """
    Returns the market hours for a given date.

    Args:
        x (dt.date | dt.datetime | str): The date to get the market hours for.
        market (str): The market to get the hours for.
        tz (str): The timezone to return the hours in.

    Returns:
        Optional[MarketHours]: A MarketHours object, or None if the market is closed.
    """
    d = _to_date(x)
    cal = _calendar(market)
    if cal is None or pd is None:
        return None
    sched = cal.schedule(start_date=d, end_date=d)
    if sched.empty:
        return None
    row = sched.iloc[0]
    tzinfo = _tz(tz)
    op = row["market_open"].to_pydatetime().astimezone(tzinfo)
    cl = row["market_close"].to_pydatetime().astimezone(tzinfo)
    return MarketHours(market_open=op, market_close=cl)


def is_market_open(
    ts: Optional[dt.datetime] = None, market: str = DEFAULT_MARKET, tz: str = LOCAL_TZ
) -> bool:
    """
    Checks if the market is open at a given time.

    Args:
        ts (Optional[dt.datetime]): The time to check.
        market (str): The market to check against.
        tz (str): The timezone to check in.

    Returns:
        bool: True if the market is open, False otherwise.
    """
    tzinfo = _tz(tz)
    ts = (
        ts.astimezone(tzinfo)
        if isinstance(ts, dt.datetime)
        else dt.datetime.now(tzinfo)
    )
    hours = market_hours(ts.date(), market=market, tz=tz)
    if hours is None:
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
