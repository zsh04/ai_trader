from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Set


def get_str(name: str, default: str = "") -> str:
    """
    Gets a string from an environment variable.

    Args:
        name (str): The name of the environment variable.
        default (str): The default value to return if the environment variable is not set.

    Returns:
        str: The value of the environment variable.
    """
    value = os.getenv(name)
    return value if value not in (None, "") else default


def get_bool(name: str, default: bool = False) -> bool:
    """
    Gets a boolean from an environment variable.

    Args:
        name (str): The name of the environment variable.
        default (bool): The default value to return if the environment variable is not set.

    Returns:
        bool: The value of the environment variable.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def get_int(name: str, default: int) -> int:
    """
    Gets an integer from an environment variable.

    Args:
        name (str): The name of the environment variable.
        default (int): The default value to return if the environment variable is not set.

    Returns:
        int: The value of the environment variable.
    """
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except Exception:
        return default


def get_float(name: str, default: float) -> float:
    """
    Gets a float from an environment variable.

    Args:
        name (str): The name of the environment variable.
        default (float): The default value to return if the environment variable is not set.

    Returns:
        float: The value of the environment variable.
    """
    raw = os.getenv(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except Exception:
        return default


def get_csv(name: str, default: str = "") -> List[str]:
    """
    Gets a list of strings from a comma-separated environment variable.

    Args:
        name (str): The name of the environment variable.
        default (str): The default value to return if the environment variable is not set.

    Returns:
        List[str]: A list of strings.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        raw = default
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def get_int_set(name: str) -> Set[int]:
    """
    Gets a set of integers from a comma-separated environment variable.

    Args:
        name (str): The name of the environment variable.

    Returns:
        Set[int]: A set of integers.
    """
    values: Set[int] = set()
    for token in get_csv(name):
        try:
            values.add(int(token))
        except Exception:
            continue
    return values


def _list_lower(name: str, default: str = "") -> List[str]:
    """
    Gets a list of lowercase strings from a comma-separated environment variable.

    Args:
        name (str): The name of the environment variable.
        default (str): The default value to return if the environment variable is not set.

    Returns:
        List[str]: A list of lowercase strings.
    """
    return [p.lower() for p in get_csv(name, default)]


@dataclass(frozen=True)
class EnvSettings:
    """
    A data class for environment settings.
    """

    PORT: int = field(default_factory=lambda: get_int("PORT", 8000))
    TZ: str = field(default_factory=lambda: get_str("TZ", "America/Los_Angeles"))
    TRADING_ENABLED: bool = field(
        default_factory=lambda: get_bool("TRADING_ENABLED", False)
    )
    PAPER_TRADING: bool = field(default_factory=lambda: get_bool("PAPER_TRADING", True))
    ALPACA_API_KEY: str = field(default_factory=lambda: get_str("ALPACA_API_KEY", ""))
    ALPACA_API_SECRET: str = field(
        default_factory=lambda: get_str("ALPACA_API_SECRET", "")
    )
    ALPACA_BASE_URL: str = field(
        default_factory=lambda: get_str(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        )
    )
    ALPACA_DATA_BASE_URL: str = field(
        default_factory=lambda: get_str(
            "ALPACA_DATA_BASE_URL", "https://data.alpaca.markets/v2"
        )
    )
    ALPACA_FEED: str = field(default_factory=lambda: get_str("ALPACA_FEED", "iex"))
    ALPACA_FORCE_YAHOO_ON_AUTH_ERROR: bool = field(
        default_factory=lambda: get_bool("ALPACA_FORCE_YAHOO_ON_AUTH_ERROR", False)
    )
    PRICE_PROVIDERS: List[str] = field(
        default_factory=lambda: _list_lower("PRICE_PROVIDERS", "alpaca,yahoo")
    )
    AZURE_STORAGE_CONNECTION_STRING: str = field(
        default_factory=lambda: get_str("AZURE_STORAGE_CONNECTION_STRING", "")
    )
    AZURE_STORAGE_ACCOUNT: str = field(
        default_factory=lambda: get_str(
            "AZURE_STORAGE_ACCOUNT_NAME", get_str("AZURE_STORAGE_ACCOUNT", "")
        )
    )
    AZURE_STORAGE_ACCOUNT_KEY: str = field(
        default_factory=lambda: get_str("AZURE_STORAGE_ACCOUNT_KEY", "")
    )
    AZURE_STORAGE_CONTAINER_NAME: str = field(
        default_factory=lambda: get_str("AZURE_STORAGE_CONTAINER_NAME", "traderdata")
    )
    AZURE_STORAGE_CONTAINER_DATA: str = field(
        default_factory=lambda: get_str("AZURE_STORAGE_CONTAINER_DATA", "trader-data")
    )
    AZURE_STORAGE_CONTAINER_MODELS: str = field(
        default_factory=lambda: get_str(
            "AZURE_STORAGE_CONTAINER_MODELS", "trader-models"
        )
    )
    PGHOST: str = field(default_factory=lambda: get_str("PGHOST", ""))
    PGPORT: int = field(default_factory=lambda: get_int("PGPORT", 5432))
    PGDATABASE: str = field(default_factory=lambda: get_str("PGDATABASE", "postgres"))
    PGUSER: str = field(default_factory=lambda: get_str("PGUSER", ""))
    PGPASSWORD: str = field(default_factory=lambda: get_str("PGPASSWORD", ""))
    PGSSLMODE: str = field(default_factory=lambda: get_str("PGSSLMODE", "require"))
    DATABASE_URL: str = field(default_factory=lambda: get_str("DATABASE_URL", ""))
    TELEGRAM_BOT_TOKEN: str = field(
        default_factory=lambda: get_str("TELEGRAM_BOT_TOKEN", "")
    )
    TELEGRAM_ALLOWED_USER_IDS: Set[int] = field(
        default_factory=lambda: get_int_set("TELEGRAM_ALLOWED_USER_IDS")
    )
    TELEGRAM_WEBHOOK_SECRET: str = field(
        default_factory=lambda: get_str("TELEGRAM_WEBHOOK_SECRET", "")
    )
    TELEGRAM_DEFAULT_CHAT_ID: str = field(
        default_factory=lambda: get_str("TELEGRAM_DEFAULT_CHAT_ID", "")
    )
    TELEGRAM_TIMEOUT_SECS: int = field(
        default_factory=lambda: get_int("TELEGRAM_TIMEOUT_SECS", 10)
    )
    HTTP_TIMEOUT_SECS: int = field(
        default_factory=lambda: get_int("HTTP_TIMEOUT_SECS", 10)
    )
    HTTP_RETRY_ATTEMPTS: int = field(
        default_factory=lambda: get_int("HTTP_RETRY_ATTEMPTS", 2)
    )
    HTTP_RETRY_BACKOFF_SEC: float = field(
        default_factory=lambda: get_float("HTTP_RETRY_BACKOFF_SEC", 1.5)
    )
    HTTP_USER_AGENT: str = field(
        default_factory=lambda: get_str(
            "HTTP_USER_AGENT", "ai-trader/0.1 (+https://example.local)"
        )
    )
    MAX_WATCHLIST: int = field(default_factory=lambda: get_int("MAX_WATCHLIST", 15))
    PRICE_MIN: float = field(default_factory=lambda: get_float("PRICE_MIN", 1.0))
    PRICE_MAX: float = field(default_factory=lambda: get_float("PRICE_MAX", 50.0))
    GAP_MIN_PCT: float = field(default_factory=lambda: get_float("GAP_MIN_PCT", 5.0))
    RVOL_MIN: float = field(default_factory=lambda: get_float("RVOL_MIN", 3.0))
    SPREAD_MAX_PCT_PRE: float = field(
        default_factory=lambda: get_float("SPREAD_MAX_PCT_PRE", 0.75)
    )
    DOLLAR_VOL_MIN_PRE: int = field(
        default_factory=lambda: get_int("DOLLAR_VOL_MIN_PRE", 1_000_000)
    )
    YF_ENABLED: bool = field(init=False)
    HTTP_RETRIES: int = field(init=False)
    HTTP_BACKOFF: float = field(init=False)
    HTTP_TIMEOUT: int = field(init=False)

    def __post_init__(self) -> None:
        """
        Initializes the derived fields.
        """
        object.__setattr__(
            self, "YF_ENABLED", any(p == "yahoo" for p in self.PRICE_PROVIDERS)
        )
        object.__setattr__(self, "HTTP_RETRIES", self.HTTP_RETRY_ATTEMPTS)
        object.__setattr__(self, "HTTP_BACKOFF", self.HTTP_RETRY_BACKOFF_SEC)
        object.__setattr__(self, "HTTP_TIMEOUT", self.HTTP_TIMEOUT_SECS)


ENV = EnvSettings()

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
