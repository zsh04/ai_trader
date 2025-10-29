import os
import json
import importlib
from fastapi.testclient import TestClient
from tests.conftest import _outbox, _clear_outbox

# Ensure tests don’t require the Telegram secret header
os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")

# Import the FastAPI app
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
    # Minimal Telegram-style update payload your route should already tolerate
    return {
        "update_id": 1001,
        "message": {
            "message_id": 111,
            "from": {"id": 999, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }

def test_ping_command_sends_reply():
    _clear_outbox()
    payload = _tg_update("/ping")
    r = client.post("/telegram/webhook", json=payload)
    assert r.status_code == 200
    ob = _outbox()
    assert len(ob) >= 1, "Expected a reply in telegram outbox"
    last_text = _last_text().lower()
    assert "pong" in last_text

def test_help_command_lists_commands():
    _clear_outbox()
    payload = _tg_update("/help")
    r = client.post("/telegram/webhook", json=payload)
    assert r.status_code == 200
    ob = _outbox()
    assert len(ob) >= 1
    last_text = _last_text().lower()
    for cmd in ("/help", "/ping", "/watchlist"):
        assert cmd in last_text

def test_unknown_command_is_graceful():
    _clear_outbox()
    payload = _tg_update("/not_a_real_cmd")
    r = client.post("/telegram/webhook", json=payload)
    assert r.status_code == 200
    ob = _outbox()
    assert len(ob) >= 1
    last_text = _last_text().lower()
    assert ("ai trader — commands" in last_text or "/help" in last_text and "/ping" in last_text and "/watchlist" in last_text)