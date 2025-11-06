# tests/unit/test_watchlist_route.py
import os

from app.domain import watchlist_service


def test_watchlist_textlist(client, monkeypatch):
    os.environ["WATCHLIST_SOURCE"] = "textlist"
    monkeypatch.setattr(
        watchlist_service, "build_watchlist", lambda source="textlist": ["aapl", "msft"]
    )

    r = client.get("/tasks/watchlist")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "textlist"
    assert data["symbols"] == ["AAPL", "MSFT"]


def test_watchlist_alpha(client, monkeypatch):
    os.environ["WATCHLIST_SOURCE"] = "alpha"
    monkeypatch.setattr(
        watchlist_service, "fetch_alpha_vantage_symbols", lambda: ["spy", "qqq"]
    )

    r = client.get("/tasks/watchlist")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "alpha"
    assert data["symbols"] == ["SPY", "QQQ"]
