
from __future__ import annotations
import os
from typing import List, Set

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v is not None else default


def _bool(name: str, default: bool = False) -> bool:
    raw = _env(name, None)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)) or default)
    except Exception:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)) or default)
    except Exception:
        return default


def _split(name: str, default: str = "") -> List[str]:
    raw = _env(name, default) or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def _split_ints(name: str) -> Set[int]:
    out: Set[int] = set()
    for part in (_env(name, "") or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out

# ------------------------------------------------------------------------------
# Core runtime
# ------------------------------------------------------------------------------
TZ                     = _env("TZ", "America/Los_Angeles") or "America/Los_Angeles"
TRADING_ENABLED        = _bool("TRADING_ENABLED", False)
PAPER_TRADING          = _bool("PAPER_TRADING", True)

# ------------------------------------------------------------------------------
# Alpaca
# ------------------------------------------------------------------------------
ALPACA_API_KEY         = _env("ALPACA_API_KEY", "") or ""
ALPACA_API_SECRET      = _env("ALPACA_API_SECRET", "") or ""
ALPACA_BASE_URL        = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets") or "https://paper-api.alpaca.markets"
ALPACA_DATA_BASE_URL   = _env("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets/v2") or "https://data.alpaca.markets/v2"
ALPACA_FEED            = _env("ALPACA_FEED", "iex") or "iex"

# Price providers
PRICE_PROVIDERS        = [p.lower() for p in _split("PRICE_PROVIDERS", "alpaca,yahoo")]
YF_ENABLED             = any(p == "yahoo" for p in PRICE_PROVIDERS)

# ------------------------------------------------------------------------------
# Azure storage
# ------------------------------------------------------------------------------
AZURE_STORAGE_CONNECTION_STRING = _env("AZURE_STORAGE_CONNECTION_STRING", "") or ""
AZURE_STORAGE_ACCOUNT           = _env("AZURE_STORAGE_ACCOUNT", "") or ""
AZURE_STORAGE_CONTAINER_DATA    = _env("AZURE_STORAGE_CONTAINER_DATA", "trader-data") or "trader-data"
AZURE_STORAGE_CONTAINER_MODELS  = _env("AZURE_STORAGE_CONTAINER_MODELS", "trader-models") or "trader-models"

# ------------------------------------------------------------------------------
# Database
# ------------------------------------------------------------------------------
PGHOST      = _env("PGHOST", "") or ""
PGPORT      = _int("PGPORT", 5432)
PGDATABASE  = _env("PGDATABASE", "postgres") or "postgres"
PGUSER      = _env("PGUSER", "") or ""
PGPASSWORD  = _env("PGPASSWORD", "") or ""
PGSSLMODE   = _env("PGSSLMODE", "require") or "require"
DATABASE_URL = _env("DATABASE_URL", "") or ""


# ------------------------------------------------------------------------------
# Telegram
# ------------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN        = _env("TELEGRAM_BOT_TOKEN", "") or ""
TELEGRAM_ALLOWED_USER_IDS = _split_ints("TELEGRAM_ALLOWED_USER_IDS")
TELEGRAM_WEBHOOK_SECRET   = _env("TELEGRAM_WEBHOOK_SECRET", "") or ""
TELEGRAM_DEFAULT_CHAT_ID  = _env("TELEGRAM_DEFAULT_CHAT_ID", "") or ""
TELEGRAM_TIMEOUT_SECS     = _int("TELEGRAM_TIMEOUT_SECS", 10)

# ------------------------------------------------------------------------------
# HTTP defaults (used by app.utils.http and providers)
# ------------------------------------------------------------------------------
HTTP_TIMEOUT_SECS      = _int("HTTP_TIMEOUT_SECS", 10)
HTTP_RETRY_ATTEMPTS    = _int("HTTP_RETRY_ATTEMPTS", 2)
HTTP_RETRY_BACKOFF_SEC = _float("HTTP_RETRY_BACKOFF_SEC", 1.5)
HTTP_USER_AGENT        = _env("HTTP_USER_AGENT", "ai-trader/0.1 (+https://example.local)") or "ai-trader/0.1"
HTTP_RETRIES        = HTTP_RETRY_ATTEMPTS
HTTP_BACKOFF        = HTTP_RETRY_BACKOFF_SEC
HTTP_TIMEOUT        = HTTP_TIMEOUT_SECS

# ------------------------------------------------------------------------------
# Scanner thresholds / caps
# ------------------------------------------------------------------------------
MAX_WATCHLIST     = _int("MAX_WATCHLIST", 15)
PRICE_MIN         = _float("PRICE_MIN", 1.0)
PRICE_MAX         = _float("PRICE_MAX", 50.0)
GAP_MIN_PCT       = _float("GAP_MIN_PCT", 5.0)
RVOL_MIN          = _float("RVOL_MIN", 3.0)
SPREAD_MAX_PCT_PRE= _float("SPREAD_MAX_PCT_PRE", 0.75)
DOLLAR_VOL_MIN_PRE= _int("DOLLAR_VOL_MIN_PRE", 1_000_000)