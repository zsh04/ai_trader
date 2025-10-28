# tests/integration/test_watchlist_route.py
import os
from fastapi.testclient import TestClient

def test_watchlist_textlist(monkeypatch):
    os.environ["WATCHLIST_SOURCE"] = "textlist"

    # mock the source to be deterministic
    import types, sys
    mod = types.ModuleType("app.source.textlist_source")
    mod.get_symbols = lambda: ["aapl", "msft", "aapl"]
    sys.modules["app.source.textlist_source"] = mod

    from app.main import app
    client = TestClient(app)

    r = client.get("/tasks/watchlist")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "textlist"
    assert data["symbols"] == ["AAPL", "MSFT"]
    assert data["count"] == 2

def test_watchlist_finviz(monkeypatch):
    os.environ["WATCHLIST_SOURCE"] = "finviz"

    import types, sys
    mod = types.ModuleType("app.source.finviz_source")
    mod.get_symbols = lambda: ["spy", "spy", "qqq"]
    sys.modules["app.source.finviz_source"] = mod

    from app.main import app
    client = TestClient(app)

    r = client.get("/tasks/watchlist")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "finviz"
    assert data["symbols"] == ["SPY", "QQQ"]
    assert data["count"] == 2