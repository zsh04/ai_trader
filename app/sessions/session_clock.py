from datetime import datetime, time

import pytz


class SessionClock:
    def __init__(self, tz: str, ranges: dict):
        self.tz = pytz.timezone(tz)
        # ranges: {'PRE': ('04:00','09:30'), ...}
        self.ranges = ranges

    def now_session(self) -> str:
        now = datetime.now(self.tz).time()
        for name, (start, end) in self.ranges.items():
            s = time.fromisoformat(start)
            e = time.fromisoformat(end)
            if s <= now < e:
                return name
        return "CLOSED"
