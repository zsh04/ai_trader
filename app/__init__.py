import logging
import os
from pathlib import Path

import sentry_sdk
from dotenv import load_dotenv
from loguru import logger
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

__version__ = "1.6.6"

# Load environment variables early so SENTRY_DSN is available for local/dev runs
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def _detect_build_version() -> str:
    explicit = os.getenv("APP_VERSION")
    if explicit:
        return explicit
    build_file = Path(__file__).resolve().parents[1] / "_build_version.txt"
    if build_file.exists():
        try:
            return build_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return "unknown"


APP_VERSION = _detect_build_version()

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
        release=APP_VERSION,
    )
else:
    logging.getLogger(__name__).info("Sentry DSN not set; Sentry disabled")

logger.info("startup: log pipeline ready")
