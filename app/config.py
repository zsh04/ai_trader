# app/config.py
from pydantic import BaseModel
import os

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads .env from project root
except Exception:
    pass

class Settings(BaseModel):
    # runtime
    port: int = int(os.getenv("PORT", "8000"))
    tz: str = os.getenv("TZ", "America/Los_Angeles")

    # alpaca
    alpaca_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret: str = os.getenv("ALPACA_API_SECRET", "")
    alpaca_base_url: str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    paper_trading: bool = os.getenv("PAPER_TRADING", "true").lower() == "true"

    # blob
    blob_account: str = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "")
    blob_key: str = os.getenv("AZURE_STORAGE_ACCOUNT_KEY", "")
    blob_container: str = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "traderdata")

    # postgres
    pg_host: str = os.getenv("PGHOST", "")
    pg_port: int = int(os.getenv("PGPORT", "5432"))
    pg_db: str = os.getenv("PGDATABASE", "")
    pg_user: str = os.getenv("PGUSER", "")
    pg_password: str = os.getenv("PGPASSWORD", "")
    pg_sslmode: str = os.getenv("PGSSLMODE", "require")

    # scan constraints
    price_min: float = float(os.getenv("PRICE_MIN", "1.0"))
    price_max: float = float(os.getenv("PRICE_MAX", "10.0"))
    gap_min_pct: float = float(os.getenv("GAP_MIN_PCT", "5.0"))
    rvol_min: float = float(os.getenv("RVOL_MIN", "3.0"))
    spread_max_pct_pre: float = float(os.getenv("SPREAD_MAX_PCT_PRE", "0.75"))
    dollar_vol_min_pre: float = float(os.getenv("DOLLAR_VOL_MIN_PRE", "1000000"))
    max_watchlist: int = int(os.getenv("MAX_WATCHLIST", "15"))

settings = Settings()