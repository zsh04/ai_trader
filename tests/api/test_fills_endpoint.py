from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.routes import fills as fills_module

client = TestClient(main_module.app)


def test_list_fills(monkeypatch):
    class DummyFill:
        def __init__(self):
            self.id = 1
            self.order_id = "run-1"
            self.symbol = "AAPL"
            self.side = "buy"
            self.qty = 2
            self.price = 150
            self.filled_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
            self.pnl = 5
            self.fee = 0.25

    class DummyRepo:
        def __init__(self, session):
            self.session = session

        def recent_trades(self, symbols=None, limit=100):
            return [DummyFill()]

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(fills_module, "TradingRepository", DummyRepo)
    monkeypatch.setattr(fills_module, "get_session", lambda: DummySession())

    resp = client.get("/fills/?limit=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["order_id"] == "run-1"
    assert data[0]["symbol"] == "AAPL"
