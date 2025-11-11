from __future__ import annotations

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


def test_router_run_offline_smoke(client):
    payload = {
        "symbol": "AAPL",
        "start": "2025-01-02T00:00:00Z",
        "strategy": "breakout",
        "offline_mode": True,
        "publish_orders": False,
        "execute_orders": False,
    }
    resp = client.post("/router/run", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"]
    assert data["order_intent"]["symbol"] == "AAPL"
