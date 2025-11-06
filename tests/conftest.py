from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs):
        return None

from app.logging_utils import setup_test_logging
from app.main import app

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"sentry_sdk\.integrations\.fastapi",
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"sentry_sdk\.integrations\.starlette",
)

os.environ.setdefault("ENV", "test")


@pytest.fixture(scope="session", autouse=True)
def load_env():
    load_dotenv(override=True)


@pytest.fixture(scope="session", autouse=True)
def configure_logging():
    setup_test_logging(Path("ai-trader-logs/"))
    yield


@pytest.fixture
def anyio_backend():
    """Force anyio-powered async tests to run under asyncio backend only."""
    return "asyncio"


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
