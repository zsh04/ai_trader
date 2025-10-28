from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture(scope="module")
def client():
    return TestClient(main_module.app)


def test_health_live_smoke(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


@pytest.mark.skipif(
    not os.getenv("TELEGRAM_BOT_TOKEN"),
    reason="TELEGRAM_BOT_TOKEN not configured",
)
def test_telegram_webhook_ping_smoke(client):
    payload = {"message": {"chat": {"id": 1}, "text": "/ping"}}
    resp = client.post(
        "/telegram/webhook",
        json=payload,
        headers={
            "X-Telegram-Bot-Api-Secret-Token": os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
        },
    )
    assert resp.status_code == 200
