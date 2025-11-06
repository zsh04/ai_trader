from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, List, Set

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


def get_str(name: str, default: str = "") -> str:
    """Return env var as a string with a sensible default."""
    value = os.getenv(name)
    return value if value not in (None, "") else default


def get_bool(name: str, default: bool = False) -> bool:
    """Coerce env var into bool (accepts 1/0, true/false, yes/no)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def get_int(name: str, default: int) -> int:
    """Coerce env var into int, falling back on conversion errors."""
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except Exception:
        return default


def get_float(name: str, default: float) -> float:
    """Coerce env var into float, falling back on conversion errors."""
    raw = os.getenv(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except Exception:
        return default


def get_int_chain(names: Iterable[str], default: int) -> int:
    """Return the first valid int from a list of env vars."""
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        candidate = str(raw).strip()
        if not candidate:
            continue
        try:
            return int(candidate)
        except Exception:
            continue
    return default


def get_float_chain(names: Iterable[str], default: float) -> float:
    """Return the first valid float from a list of env vars."""
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        candidate = str(raw).strip()
        if not candidate:
            continue
        try:
            return float(candidate)
        except Exception:
            continue
    return default


def get_csv(name: str, default: str = "") -> List[str]:
    """Parse comma-delimited strings into a list of trimmed tokens."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        raw = default
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def get_int_set(name: str) -> Set[int]:
    """Parse comma-delimited ints into a set."""
    values: Set[int] = set()
    for token in get_csv(name):
        try:
            values.add(int(token))
        except Exception:
            continue
    return values


def _list_lower(name: str, default: str = "") -> List[str]:
    return [p.lower() for p in get_csv(name, default)]


@dataclass(frozen=True)
class EnvSettings:
    """Runtime configuration sourced from environment variables."""

    #: HTTP port for FastAPI server.
    PORT: int = field(default_factory=lambda: get_int("PORT", 8000))
    #: IANA timezone used for scheduling/logging.
    TZ: str = field(default_factory=lambda: get_str("TZ", "America/Los_Angeles"))
    #: Enables live trading hooks when true.
    TRADING_ENABLED: bool = field(
        default_factory=lambda: get_bool("TRADING_ENABLED", False)
    )
    #: Whether to default to Alpaca paper trading endpoints.
    PAPER_TRADING: bool = field(default_factory=lambda: get_bool("PAPER_TRADING", True))

    #: Alpaca REST API key ID.
    ALPACA_API_KEY: str = field(default_factory=lambda: get_str("ALPACA_API_KEY", ""))
    #: Alpaca REST API secret.
    ALPACA_API_SECRET: str = field(
        default_factory=lambda: get_str("ALPACA_API_SECRET", "")
    )
    #: Base URL for order routing.
    ALPACA_BASE_URL: str = field(
        default_factory=lambda: get_str(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        )
    )
    #: Base URL for Alpaca market data API.
    ALPACA_DATA_BASE_URL: str = field(
        default_factory=lambda: get_str(
            "ALPACA_DATA_BASE_URL", "https://data.alpaca.markets/v2"
        )
    )
    #: Preferred Alpaca data feed (iex/sip).
    ALPACA_FEED: str = field(default_factory=lambda: get_str("ALPACA_FEED", "iex"))
    #: Force Yahoo fallback when Alpaca authentication fails.
    ALPACA_FORCE_YAHOO_ON_AUTH_ERROR: bool = field(
        default_factory=lambda: get_bool("ALPACA_FORCE_YAHOO_ON_AUTH_ERROR", False)
    )

    #: Alpha Vantage market data API key.
    ALPHAVANTAGE_API_KEY: str = field(
        default_factory=lambda: get_str("ALPHAVANTAGE_API_KEY", "")
    )
    #: Finnhub API token.
    FINNHUB_API_KEY: str = field(default_factory=lambda: get_str("FINNHUB_API_KEY", ""))
    #: Twelve Data API key for redundancy.
    TWELVEDATA_API_KEY: str = field(
        default_factory=lambda: get_str("TWELVEDATA_API_KEY", "")
    )

    #: Ordered preference of upstream price providers.
    PRICE_PROVIDERS: List[str] = field(
        default_factory=lambda: _list_lower("PRICE_PROVIDERS", "alpaca,yahoo")
    )

    #: Azure storage connection string (if provided).
    AZURE_STORAGE_CONNECTION_STRING: str = field(
        default_factory=lambda: get_str("AZURE_STORAGE_CONNECTION_STRING", "")
    )
    #: Azure storage account when using shared key auth (supports legacy names).
    AZURE_STORAGE_ACCOUNT: str = field(
        default_factory=lambda: get_str(
            "AZURE_STORAGE_ACCOUNT_NAME", get_str("AZURE_STORAGE_ACCOUNT", "")
        )
    )
    #: Azure storage shared key credential.
    AZURE_STORAGE_ACCOUNT_KEY: str = field(
        default_factory=lambda: get_str("AZURE_STORAGE_ACCOUNT_KEY", "")
    )
    #: Container used for general data artifacts (legacy name support).
    AZURE_STORAGE_CONTAINER_NAME: str = field(
        default_factory=lambda: get_str("AZURE_STORAGE_CONTAINER_NAME", "traderdata")
    )
    #: Container used for general data artifacts.
    AZURE_STORAGE_CONTAINER_DATA: str = field(
        default_factory=lambda: get_str("AZURE_STORAGE_CONTAINER_DATA", "trader-data")
    )
    #: Container used for ML/strategy models.
    AZURE_STORAGE_CONTAINER_MODELS: str = field(
        default_factory=lambda: get_str(
            "AZURE_STORAGE_CONTAINER_MODELS", "trader-models"
        )
    )

    #: Postgres host name.
    PGHOST: str = field(default_factory=lambda: get_str("PGHOST", ""))
    #: Postgres port.
    PGPORT: int = field(default_factory=lambda: get_int("PGPORT", 5432))
    #: Primary database name.
    PGDATABASE: str = field(default_factory=lambda: get_str("PGDATABASE", "postgres"))
    #: Postgres username.
    PGUSER: str = field(default_factory=lambda: get_str("PGUSER", ""))
    #: Postgres password.
    PGPASSWORD: str = field(default_factory=lambda: get_str("PGPASSWORD", ""))
    #: SSL mode for Postgres connection.
    PGSSLMODE: str = field(default_factory=lambda: get_str("PGSSLMODE", "require"))
    #: Full DATABASE_URL if provided (takes precedence elsewhere).
    DATABASE_URL: str = field(default_factory=lambda: get_str("DATABASE_URL", ""))

    #: Telegram Bot API token.
    TELEGRAM_BOT_TOKEN: str = field(
        default_factory=lambda: get_str("TELEGRAM_BOT_TOKEN", "")
    )
    #: Comma-delimited list of authorized Telegram user IDs.
    TELEGRAM_ALLOWED_USER_IDS: Set[int] = field(
        default_factory=lambda: get_int_set("TELEGRAM_ALLOWED_USER_IDS")
    )
    #: Telegram webhook secret for FastAPI verification.
    TELEGRAM_WEBHOOK_SECRET: str = field(
        default_factory=lambda: get_str("TELEGRAM_WEBHOOK_SECRET", "")
    )
    #: Default chat/channel for proactive notifications.
    TELEGRAM_DEFAULT_CHAT_ID: str = field(
        default_factory=lambda: get_str("TELEGRAM_DEFAULT_CHAT_ID", "")
    )
    #: HTTP timeout used by Telegram client.
    TELEGRAM_TIMEOUT_SECS: int = field(
        default_factory=lambda: get_int("TELEGRAM_TIMEOUT_SECS", 10)
    )

    #: Default HTTP request timeout (seconds).
    HTTP_TIMEOUT_SECS: int = field(
        default_factory=lambda: get_int_chain(("HTTP_TIMEOUT", "HTTP_TIMEOUT_SECS"), 10)
    )
    #: Default retry attempts for outbound HTTP.
    HTTP_RETRY_ATTEMPTS: int = field(
        default_factory=lambda: get_int_chain(
            ("HTTP_RETRIES", "HTTP_RETRY_ATTEMPTS"), 2
        )
    )
    #: Default retry backoff for outbound HTTP.
    HTTP_RETRY_BACKOFF_SEC: float = field(
        default_factory=lambda: get_float_chain(
            ("HTTP_BACKOFF", "HTTP_RETRY_BACKOFF_SEC"), 1.5
        )
    )
    #: HTTP user-agent header for outbound requests.
    HTTP_USER_AGENT: str = field(
        default_factory=lambda: get_str(
            "HTTP_USER_AGENT", "ai-trader/0.1 (+https://example.local)"
        )
    )

    #: Maximum symbols in generated watchlists.
    MAX_WATCHLIST: int = field(default_factory=lambda: get_int("MAX_WATCHLIST", 15))
    #: Minimum price allowed by scanners.
    PRICE_MIN: float = field(default_factory=lambda: get_float("PRICE_MIN", 1.0))
    #: Maximum price allowed by scanners.
    PRICE_MAX: float = field(default_factory=lambda: get_float("PRICE_MAX", 50.0))
    #: Minimum gap percentage filter.
    GAP_MIN_PCT: float = field(default_factory=lambda: get_float("GAP_MIN_PCT", 5.0))
    #: Minimum relative-volume threshold.
    RVOL_MIN: float = field(default_factory=lambda: get_float("RVOL_MIN", 3.0))
    #: Maximum allowed spread percentage in pre-market.
    SPREAD_MAX_PCT_PRE: float = field(
        default_factory=lambda: get_float("SPREAD_MAX_PCT_PRE", 0.75)
    )
    #: Minimum pre-market dollar volume.
    DOLLAR_VOL_MIN_PRE: int = field(
        default_factory=lambda: get_int("DOLLAR_VOL_MIN_PRE", 1_000_000)
    )

    #: Convenience mirror of PRICE_PROVIDERS containing "yahoo".
    YF_ENABLED: bool = field(init=False)
    #: Convenience alias for HTTP retries.
    HTTP_RETRIES: int = field(init=False)
    #: Convenience alias for HTTP backoff seconds.
    HTTP_BACKOFF: float = field(init=False)
    #: Convenience alias for HTTP timeout seconds.
    HTTP_TIMEOUT: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "YF_ENABLED", any(p == "yahoo" for p in self.PRICE_PROVIDERS)
        )
        object.__setattr__(self, "HTTP_RETRIES", self.HTTP_RETRY_ATTEMPTS)
        object.__setattr__(self, "HTTP_BACKOFF", self.HTTP_RETRY_BACKOFF_SEC)
        object.__setattr__(self, "HTTP_TIMEOUT", self.HTTP_TIMEOUT_SECS)


ENV = EnvSettings()

# Backward compatible module-level aliases -------------------------------------------------
PORT = ENV.PORT
TZ = ENV.TZ
TRADING_ENABLED = ENV.TRADING_ENABLED
PAPER_TRADING = ENV.PAPER_TRADING

ALPACA_API_KEY = ENV.ALPACA_API_KEY
ALPACA_API_SECRET = ENV.ALPACA_API_SECRET
ALPACA_BASE_URL = ENV.ALPACA_BASE_URL
ALPACA_DATA_BASE_URL = ENV.ALPACA_DATA_BASE_URL
ALPACA_FEED = ENV.ALPACA_FEED
ALPACA_FORCE_YAHOO_ON_AUTH_ERROR = ENV.ALPACA_FORCE_YAHOO_ON_AUTH_ERROR
ALPHAVANTAGE_API_KEY = ENV.ALPHAVANTAGE_API_KEY
FINNHUB_API_KEY = ENV.FINNHUB_API_KEY
TWELVEDATA_API_KEY = ENV.TWELVEDATA_API_KEY
PRICE_PROVIDERS = ENV.PRICE_PROVIDERS
YF_ENABLED = ENV.YF_ENABLED

AZURE_STORAGE_CONNECTION_STRING = ENV.AZURE_STORAGE_CONNECTION_STRING
AZURE_STORAGE_ACCOUNT = ENV.AZURE_STORAGE_ACCOUNT
AZURE_STORAGE_ACCOUNT_KEY = ENV.AZURE_STORAGE_ACCOUNT_KEY
AZURE_STORAGE_CONTAINER_NAME = ENV.AZURE_STORAGE_CONTAINER_NAME
AZURE_STORAGE_CONTAINER_DATA = ENV.AZURE_STORAGE_CONTAINER_DATA
AZURE_STORAGE_CONTAINER_MODELS = ENV.AZURE_STORAGE_CONTAINER_MODELS

PGHOST = ENV.PGHOST
PGPORT = ENV.PGPORT
PGDATABASE = ENV.PGDATABASE
PGUSER = ENV.PGUSER
PGPASSWORD = ENV.PGPASSWORD
PGSSLMODE = ENV.PGSSLMODE
DATABASE_URL = ENV.DATABASE_URL

TELEGRAM_BOT_TOKEN = ENV.TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_IDS = ENV.TELEGRAM_ALLOWED_USER_IDS
TELEGRAM_WEBHOOK_SECRET = ENV.TELEGRAM_WEBHOOK_SECRET
TELEGRAM_DEFAULT_CHAT_ID = ENV.TELEGRAM_DEFAULT_CHAT_ID
TELEGRAM_TIMEOUT_SECS = ENV.TELEGRAM_TIMEOUT_SECS

HTTP_TIMEOUT_SECS = ENV.HTTP_TIMEOUT_SECS
HTTP_RETRY_ATTEMPTS = ENV.HTTP_RETRY_ATTEMPTS
HTTP_RETRY_BACKOFF_SEC = ENV.HTTP_RETRY_BACKOFF_SEC
HTTP_USER_AGENT = ENV.HTTP_USER_AGENT
HTTP_RETRIES = ENV.HTTP_RETRIES
HTTP_BACKOFF = ENV.HTTP_BACKOFF
HTTP_TIMEOUT = ENV.HTTP_TIMEOUT

MAX_WATCHLIST = ENV.MAX_WATCHLIST
PRICE_MIN = ENV.PRICE_MIN
PRICE_MAX = ENV.PRICE_MAX
GAP_MIN_PCT = ENV.GAP_MIN_PCT
RVOL_MIN = ENV.RVOL_MIN
SPREAD_MAX_PCT_PRE = ENV.SPREAD_MAX_PCT_PRE
DOLLAR_VOL_MIN_PRE = ENV.DOLLAR_VOL_MIN_PRE
