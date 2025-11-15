from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class TimeWindow:
    label: str
    delta: timedelta

    def range(self) -> tuple[datetime, datetime]:
        now = datetime.now(tz=timezone.utc)
        return now - self.delta, now


DEFAULT_WINDOWS = [
    TimeWindow("1D", timedelta(days=1)),
    TimeWindow("5D", timedelta(days=5)),
    TimeWindow("1M", timedelta(days=30)),
]
