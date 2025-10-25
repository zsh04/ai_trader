from datetime import datetime, timezone

def utc_now():
    """Return current UTC datetime with tzinfo."""
    return datetime.now(timezone.utc)

def utc_iso():
    """Return current UTC datetime as ISO string."""
    return utc_now().isoformat()