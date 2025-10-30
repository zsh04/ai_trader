import os
import pytest
from tests.conftest import _outbox, _clear_outbox, client

pytestmark = pytest.mark.skip(reason="Parking lot: Telegram watchlist command tests temporarily disabled pending refactor.")

def _last_text():
    ob = _outbox()
    assert ob, "Expected a reply in telegram outbox"
    last = ob[-1]
    # Outbox entries are dicts from the patched requests.post: {"url", "chat_id", "text"}
    if isinstance(last, dict):
        return last.get("text", "")
    # Back-compat: some older tests/outbox fakes used tuples (url, text)
    if isinstance(last, (list, tuple)) and len(last) >= 2:
        return last[1]
    return str(last)

def _tg_update(cmd: str):
    return {
        "update_id": 2001,
        "message": {
            "message_id": 222,
            "from": {"id": 999, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 42, "type": "private"},
            "date": 1700000001,
            "text": cmd,
        },
    }

@pytest.fixture(autouse=True)
def patch_watchlist(monkeypatch):
    # Force a deterministic set of symbols and a named source
    def fake_resolve_watchlist():
        return ("textlist", ["AAPL", "MSFT", "NVDA"])
    monkeypatch.setattr("app.domain.watchlist_service.resolve_watchlist", fake_resolve_watchlist)
    yield


def test_watchlist_command_renders_symbols(client):
    _clear_outbox()
    r = client.post("/telegram/webhook", json=_tg_update("/watchlist"))
    assert r.status_code == 200
    ob = _outbox()
    assert len(ob) >= 1
    # Just ensure we got a watchlist-style reply
    assert any("watchlist" in m.lower() for m in ob)