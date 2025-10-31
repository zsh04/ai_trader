from __future__ import annotations

import logging
import zoneinfo
from datetime import datetime, time, timezone

log = logging.getLogger(__name__)

ET = zoneinfo.ZoneInfo("America/New_York")


def now_utc() -> datetime:
    """
    Returns the current UTC datetime.

    Returns:
        datetime: The current UTC datetime.
    """
    return datetime.now(timezone.utc)


def session_for(dt_utc: datetime) -> str:
    """
    Determines the trading session for a given UTC datetime.

    Args:
        dt_utc (datetime): The UTC datetime.

    Returns:
        str: The trading session.
    """
    try:
        dt_et = dt_utc.astimezone(ET)
        t_ = dt_et.time()
        if time(4, 0) <= t_ < time(9, 30):
            return "premarket"
        if time(9, 30) <= t_ < time(16, 0):
            return "regular"
        if time(16, 0) <= t_ < time(20, 0):
            return "after"
        return "closed"
    except Exception as e:
        log.warning("session_for failed: %s", e)
        return "unknown"
