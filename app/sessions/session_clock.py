import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)


class SessionClock:
    """
    A class for managing trading sessions.
    """
    def __init__(self, tz: str, ranges: dict):
        """
        Initializes the SessionClock.

        Args:
            tz (str): The timezone to use.
            ranges (dict): A dictionary of session ranges.
        """
        self.tz = ZoneInfo(tz)
        self.ranges = ranges

    def now_session(self) -> str:
        """
        Returns the current trading session.

        Returns:
            str: The current trading session.
        """
        try:
            now = datetime.now(self.tz).time()
            for name, (start, end) in self.ranges.items():
                s = time.fromisoformat(start)
                e = time.fromisoformat(end)
                if s <= now < e:
                    log.debug("SessionClock active: %s (%s-%s)", name, start, end)
                    return name
            log.debug("SessionClock: no active session at %s", now)
            return "CLOSED"
        except Exception as e:
            log.error("SessionClock error: %s", e)
            return "CLOSED"

    def next_session(self) -> tuple[str, str] | None:
        """
        Returns the next trading session.

        Returns:
            tuple[str, str] | None: A tuple of (session_name, start_time), or None if no next session.
        """
        try:
            now = datetime.now(self.tz).time()
            for name, (start, _) in self.ranges.items():
                if now < time.fromisoformat(start):
                    return name, start
            return None
        except Exception as e:
            log.error("SessionClock.next_session error: %s", e)
            return None
