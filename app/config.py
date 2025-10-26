from __future__ import annotations

from dataclasses import dataclass, field

from app import __version__
from app.utils.env import ENV


@dataclass(frozen=True)
class Settings:
    """Application settings derived from environment variables."""

    #: Semantic version string exposed to FastAPI/open health endpoints.
    VERSION: str = __version__
    #: HTTP port for the API server (used by CLI wrappers/process managers).
    port: int = ENV.PORT
    #: Default timezone for scheduling/logging.
    tz: str = ENV.TZ

    #: Alpaca API key ID.
    alpaca_key: str = ENV.ALPACA_API_KEY
    #: Alpaca API secret.
    alpaca_secret: str = ENV.ALPACA_API_SECRET
    #: Alpaca REST endpoint base URL.
    alpaca_base_url: str = ENV.ALPACA_BASE_URL
    #: Whether the deployment is using paper trading.
    paper_trading: bool = ENV.PAPER_TRADING

    #: Azure storage account name for blob access.
    blob_account: str = ENV.AZURE_STORAGE_ACCOUNT
    #: Azure blob shared key credential (if not using connection string).
    blob_key: str = ENV.AZURE_STORAGE_ACCOUNT_KEY
    #: Default blob container for persistent artifacts.
    blob_container: str = (
        ENV.AZURE_STORAGE_CONTAINER_NAME or ENV.AZURE_STORAGE_CONTAINER_DATA
    )

    #: Postgres host.
    pg_host: str = ENV.PGHOST
    #: Postgres port.
    pg_port: int = ENV.PGPORT
    #: Postgres database name.
    pg_db: str = ENV.PGDATABASE
    #: Postgres username.
    pg_user: str = ENV.PGUSER
    #: Postgres password.
    pg_password: str = ENV.PGPASSWORD
    #: Postgres SSL mode.
    pg_sslmode: str = ENV.PGSSLMODE

    #: Minimum symbol price accepted by scanners.
    price_min: float = ENV.PRICE_MIN
    #: Maximum symbol price accepted by scanners.
    price_max: float = ENV.PRICE_MAX
    #: Minimum gap percentage filter.
    gap_min_pct: float = ENV.GAP_MIN_PCT
    #: Minimum relative volume filter.
    rvol_min: float = ENV.RVOL_MIN
    #: Maximum acceptable pre-market spread (percentage).
    spread_max_pct_pre: float = ENV.SPREAD_MAX_PCT_PRE
    #: Minimum pre-market dollar volume.
    dollar_vol_min_pre: int = ENV.DOLLAR_VOL_MIN_PRE
    #: Maximum symbols returned by watchlist builder.
    max_watchlist: int = ENV.MAX_WATCHLIST


settings = Settings()

__all__ = ["settings", "Settings"]
