import sys

import pytest
from dotenv import load_dotenv

# Load .env and force a test bypass for webhook secret
os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")
load_dotenv(override=True)


@pytest.fixture(scope="session", autouse=True)
def load_env():
    """Ensure .env is loaded for all tests."""
    load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def _reload_env_modules():
    """Make sure modules that cache ENV see the test env values."""
    # If modules were imported earlier (by some editor plugin or prior tests),
    # reload them so they re-read env.
    for mod in ("app.config", "app.wiring.telegram_router"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    yield
