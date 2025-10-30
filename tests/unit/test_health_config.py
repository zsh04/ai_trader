from starlette.testclient import TestClient
from app.main import app
import os

client = TestClient(app)

def test_health_config_masks_and_status(monkeypatch):
    # Simulate prod-ish env
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "AA1234567890ZZ")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")
    monkeypatch.setenv("ALPACA_API_KEY", "PK_TEST_ABCDEF")
    monkeypatch.setenv("ALPACA_FEED", "iex")
    monkeypatch.setenv("WATCHLIST_SOURCE", "textlist")

    r = client.get("/health/config")
    assert r.status_code == 200
    data = r.json()

    # status & booleans present
    assert data["status"] in ("ok", "degraded")
    assert "has_telegram_token" in data["validation"]
    assert "has_db_url" in data["validation"]
    assert "has_alpaca_keys" in data["validation"]

    # mask format: first 2 + last 4 visible, middle masked
    masked = data["env"]["TELEGRAM_BOT_TOKEN"]
    assert masked.startswith("AA")
    assert masked.endswith("ZZ")
    assert "*" in masked