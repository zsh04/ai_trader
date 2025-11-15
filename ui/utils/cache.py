from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Dict, Tuple

_CACHE: Dict[
    Tuple[str, Tuple[Any, ...], Tuple[Tuple[str, Any], ...]], Tuple[float, Any]
] = {}


def cache_data(ttl_seconds: int = 60):
    """Simple TTL cache decorator for service calls."""

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (
                func.__module__ + "." + func.__name__,
                args,
                tuple(sorted(kwargs.items())),
            )
            now = time.time()
            if key in _CACHE:
                ts, value = _CACHE[key]
                if now - ts < ttl_seconds:
                    return value
            value = func(*args, **kwargs)
            _CACHE[key] = (now, value)
            return value

        def bust(*bust_args, **bust_kwargs):
            key = (
                func.__module__ + "." + func.__name__,
                bust_args,
                tuple(sorted(bust_kwargs.items())),
            )
            _CACHE.pop(key, None)

        wrapper.bust = bust  # type: ignore[attr-defined]
        return wrapper

    return decorator
