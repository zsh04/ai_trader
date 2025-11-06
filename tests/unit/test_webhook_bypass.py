from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_webhook_bypass_header_non_prod(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "shhh")
    # No secret provided, but debug header present
    payload = {
        "update_id": 1001,
        "message": {"chat": {"id": 42}, "from": {"id": 999}, "text": "/ping"},
    }
    r = client.post(
        "/telegram/webhook", json=payload, headers={"X-Debug-Telegram": "1"}
    )
    assert r.status_code == 200
