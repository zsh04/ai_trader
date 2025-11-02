from datetime import datetime, time
from zoneinfo import ZoneInfo

from loguru import logger


class SessionClock:
    def __init__(self, tz: str, ranges: dict):
        self.tz = ZoneInfo(tz)
        # ranges: {'PRE': ('04:00','09:30'), ...}
        self.ranges = ranges

    def now_session(self) -> str:
        try:
            now = datetime.now(self.tz).time()
            for name, (start, end) in self.ranges.items():
                s = time.fromisoformat(start)
                e = time.fromisoformat(end)
                if s <= now < e:
                    logger.debug("SessionClock active: {} ({}-{})", name, start, end)
                    return name
            logger.debug("SessionClock: no active session at {}", now)
            return "CLOSED"
        except Exception as e:
            logger.error("SessionClock error: {}", e)
            return "CLOSED"

    def next_session(self) -> tuple[str, str] | None:
        """Return the next session name and start time."""
        try:
            now = datetime.now(self.tz).time()
            for name, (start, _) in self.ranges.items():
                if now < time.fromisoformat(start):
                    return name, start
            return None
        except Exception as e:
            logger.error("SessionClock.next_session error: {}", e)
            return None
