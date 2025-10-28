# tests/wiring/test_watchlist_telegram.py
import types
from starlette.testclient import TestClient
from pytest import MonkeyPatch

def make_client(monkeypatch: MonkeyPatch) -> TestClient:
    import sys

    # stub sources
    finviz = types.ModuleType("app.source.finviz_source")
    finviz.get_symbols = lambda scanner=None: ["AAPL", "MSFT", "aapl"]
    sys.modules["app.source.finviz_source"] = finviz

    textlist = types.ModuleType("app.source.textlist_source")
    textlist.get_symbols = lambda scanner=None: ["TSLA", "NVDA"]
    sys.modules["app.source.textlist_source"] = textlist

    # stub telegram
    fake_sent = {"msgs": []}
    tgmod = types.ModuleType("app.wiring.telegram")
    class FakeTG:
        def smart_send(self, chat_id, text, **kwargs):
            fake_sent["msgs"].append(text)
    tgmod.get_telegram = lambda: FakeTG()
    tgmod.TelegramClient = FakeTG
    sys.modules["app.wiring.telegram"] = tgmod

    from app.main import app
    c = TestClient(app)
    c._sent = fake_sent
    return c

def test_watchlist_command_auto(monkeypatch: MonkeyPatch):
    c = make_client(monkeypatch)
    resp = c.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 1}, "text": "/watchlist auto - 5 alpha"}},
    )
    assert resp.status_code == 200
    last = c._sent["msgs"][-1]
    # deduped and alpha-limited to 5
    assert "AAPL" in last and "MSFT" in last

def test_watchlist_command_finviz_limit(monkeypatch: MonkeyPatch):
    c = make_client(monkeypatch)
    resp = c.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 1}, "text": "/watchlist finviz top_gainers 1"}},
    )
    assert resp.status_code == 200
    last = c._sent["msgs"][-1]
    # limited to 1
    assert "Watchlist (1)" in last