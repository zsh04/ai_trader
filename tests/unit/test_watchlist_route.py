# tests/integration/test_watchlist_route.py
import os, sys, types
from tests.conftest import _outbox, _clear_outbox, client

def test_watchlist_textlist(client, monkeypatch):
    os.environ["WATCHLIST_SOURCE"] = "textlist"
    mod = types.ModuleType("app.source.textlist_source")
    mod.get_symbols = lambda: ["aapl", "msft", "aapl"]
    sys.modules["app.source.textlist_source"] = mod

    r = client.get("/tasks/watchlist")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "textlist"
    assert data["symbols"] == ["AAPL", "MSFT"]


def test_watchlist_finviz(client, monkeypatch):
    os.environ["WATCHLIST_SOURCE"] = "finviz"
    mod = types.ModuleType("app.source.finviz_source")
    mod.get_symbols = lambda: ["spy", "spy", "qqq"]
    sys.modules["app.source.finviz_source"] = mod

    r = client.get("/tasks/watchlist")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "finviz"
    assert data["symbols"] == ["SPY", "QQQ"]