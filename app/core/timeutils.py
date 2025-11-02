from __future__ import annotations

import zoneinfo
from datetime import datetime, time, timezone

from loguru import logger

# Eastern Timezone aware (handles DST via IANA database)
ET = zoneinfo.ZoneInfo("America/New_York")


def now_utc() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


def session_for(dt_utc: datetime) -> str:
    """
    Determine the trading session (premarket, regular, after, closed) for a UTC timestamp.
    Uses US Eastern (NYSE/NASDAQ) hours by default.
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
        logger.warning("session_for failed: {}", e)
        return "unknown"
