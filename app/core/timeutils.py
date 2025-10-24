from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

ET = timezone(
    timedelta(hours=-5)
)  # Will not auto-DST flip; adjust if needed elsewhere.


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def session_for(dt_utc: datetime) -> str:
    # naive session splitter; tune with a proper market calendar later
    dt_et = dt_utc.astimezone(ET)
    t_ = dt_et.time()
    if time(4, 0) <= t_ < time(9, 30):
        return "premarket"
    if time(9, 30) <= t_ < time(16, 0):
        return "regular"
    if time(16, 0) <= t_ < time(20, 0):
        return "after"
    return "closed"
