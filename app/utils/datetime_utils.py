from datetime import datetime, timezone


def utc_now():
    """
    Returns the current UTC datetime.

    Returns:
        datetime: The current UTC datetime.
    """
    return datetime.now(timezone.utc)


def utc_iso():
    """
    Returns the current UTC datetime as an ISO string.

    Returns:
        str: The current UTC datetime as an ISO string.
    """
    return utc_now().isoformat()
