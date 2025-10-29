import os
import importlib
from fastapi.testclient import TestClient
import pytest
from tests.conftest import _outbox, _clear_outbox

os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")

from app.main import app  # noqa: E402

client = TestClient(app)

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

def _tg_update(text: str, chat_id: int = 42):
    return {
        "update_id": 2001,
        "message": {
            "message_id": 222,
            "from": {"id": 999, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000001,
            "text": text,
        },
    }

@pytest.fixture(autouse=True)
def patch_watchlist(monkeypatch):
    # Force a deterministic set of symbols and a named source
    def fake_resolve_watchlist():
        return ("textlist", ["AAPL", "MSFT", "NVDA"])
    monkeypatch.setattr("app.domain.watchlist_service.resolve_watchlist", fake_resolve_watchlist)
    yield

def test_watchlist_command_renders_symbols():
    _clear_outbox()
    payload = _tg_update("/watchlist")
    r = client.post("/telegram/webhook", json=payload)
    assert r.status_code == 200
    ob = _outbox()
    assert len(ob) >= 1
    last_text = _last_text().lower()
    # Minimal proof the symbols flowed through
    assert "aapl" in last_text
    assert "msft" in last_text
    assert "nvda" in last_text