from __future__ import annotations

from dataclasses import dataclass

from app import __version__
from app.utils.env import ENV


@dataclass(frozen=True)
class Settings:
    """
    A data class for application settings.

    Attributes:
        VERSION (str): The application version.
        port (int): The port to run the application on.
        tz (str): The timezone to use.
        alpaca_key (str): The Alpaca API key.
        alpaca_secret (str): The Alpaca API secret.
        alpaca_base_url (str): The Alpaca base URL.
        paper_trading (bool): Whether to use paper trading.
        blob_account (str): The Azure blob storage account.
        blob_key (str): The Azure blob storage key.
        blob_container (str): The Azure blob storage container.
        pg_host (str): The PostgreSQL host.
        pg_port (int): The PostgreSQL port.
        pg_db (str): The PostgreSQL database.
        pg_user (str): The PostgreSQL user.
        pg_password (str): The PostgreSQL password.
        pg_sslmode (str): The PostgreSQL SSL mode.
        database_url (str): The database URL.
        price_min (float): The minimum price for a symbol.
        price_max (float): The maximum price for a symbol.
        gap_min_pct (float): The minimum gap percentage.
        rvol_min (float): The minimum relative volume.
        spread_max_pct_pre (float): The maximum pre-market spread percentage.
        dollar_vol_min_pre (int): The minimum pre-market dollar volume.
        max_watchlist (int): The maximum number of symbols in a watchlist.
    """

    VERSION: str = __version__
    port: int = ENV.PORT
    tz: str = ENV.TZ
    alpaca_key: str = ENV.ALPACA_API_KEY
    alpaca_secret: str = ENV.ALPACA_API_SECRET
    alpaca_base_url: str = ENV.ALPACA_BASE_URL
    paper_trading: bool = ENV.PAPER_TRADING
    blob_account: str = ENV.AZURE_STORAGE_ACCOUNT
    blob_key: str = ENV.AZURE_STORAGE_ACCOUNT_KEY
    blob_container: str = (
        ENV.AZURE_STORAGE_CONTAINER_NAME or ENV.AZURE_STORAGE_CONTAINER_DATA
    )
    pg_host: str = ENV.PGHOST
    pg_port: int = ENV.PGPORT
    pg_db: str = ENV.PGDATABASE
    pg_user: str = ENV.PGUSER
    pg_password: str = ENV.PGPASSWORD
    pg_sslmode: str = ENV.PGSSLMODE
    database_url: str = ENV.DATABASE_URL
    price_min: float = ENV.PRICE_MIN
    price_max: float = ENV.PRICE_MAX
    gap_min_pct: float = ENV.GAP_MIN_PCT
    rvol_min: float = ENV.RVOL_MIN
    spread_max_pct_pre: float = ENV.SPREAD_MAX_PCT_PRE
    dollar_vol_min_pre: int = ENV.DOLLAR_VOL_MIN_PRE
    max_watchlist: int = ENV.MAX_WATCHLIST


settings = Settings()

__all__ = ["settings", "Settings"]
