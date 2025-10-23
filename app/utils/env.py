from __future__ import annotations
import os
from typing import Optional, List

def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        from app.config import settings  # optional pydantic settings
        if hasattr(settings, key):
            return getattr(settings, key)
    except Exception:
        pass
    return os.environ.get(key, default)

ALPACA_API_KEY        = _env("ALPACA_API_KEY", "") or ""
ALPACA_API_SECRET     = _env("ALPACA_API_SECRET", "") or ""
ALPACA_BASE_URL       = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_BASE_URL  = _env("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets/v2")
ALPACA_FEED           = _env("ALPACA_FEED", "iex") or "iex"

HTTP_TIMEOUT_SECS     = float(_env("HTTP_TIMEOUT_SECS", "10") or 10)
HTTP_RETRIES          = int(_env("HTTP_RETRIES", "2") or 2)
HTTP_RETRY_BACKOFF    = float(_env("HTTP_RETRY_BACKOFF", "0.5") or 0.5)

PRICE_PROVIDERS: List[str] = [s.strip() for s in (_env("PRICE_PROVIDERS", "alpaca,yahoo") or "").split(",") if s.strip()]
YF_ENABLED            = any(p.lower() == "yahoo" for p in PRICE_PROVIDERS)
YF_TIMEOUT_SECS       = float(_env("YF_TIMEOUT_SECS", "6") or 6)

DATABASE_URL          = _env("DATABASE_URL", "") or ""