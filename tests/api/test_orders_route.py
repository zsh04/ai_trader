from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.routes import orders as orders_module

client = TestClient(main_module.app)


def test_list_orders(monkeypatch):
    sample = [
        {
            "id": "run-1",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 5,
            "status": "pending",
            "submitted_at": datetime(2025, 1, 2, tzinfo=timezone.utc),
            "strategy": "breakout",
            "run_id": "run-1",
            "broker_order_id": None,
        }
    ]
    monkeypatch.setattr(orders_module, "_list_recent_orders", lambda limit: sample)
    resp = client.get("/orders?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["status"] == "pending"
