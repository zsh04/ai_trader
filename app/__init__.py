import os
import logging
from pathlib import Path

from dotenv import load_dotenv
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

__version__ = "1.6.6"

# Load environment variables early so SENTRY_DSN is available for local/dev runs
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# Initialize Sentry as early as possible (only if DSN is provided)
_dsn = os.getenv("SENTRY_DSN")
if _dsn:
    sentry_sdk.init(
        dsn=_dsn,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=1.0,
        profiles_sample_rate=0.0,
        environment=os.getenv("APP_ENV", "prod"),
        release=os.getenv("APP_VERSION", "unknown"),
    )
else:
    logging.getLogger(__name__).info("Sentry DSN not set; Sentry disabled")

from loguru import logger
logger.info("startup: log pipeline ready")
