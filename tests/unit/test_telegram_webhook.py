import os

import pytest

from tests.conftest import _clear_outbox, _outbox

pytestmark = pytest.mark.skip(
    reason="Parking lot: Telegram webhook tests temporarily disabled pending refactor."
)

os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")


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
        "update_id": 1001,
        "message": {
            "message_id": 111,
            "from": {"id": 999, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 42, "type": "private"},
            "date": 1700000000,
            "text": cmd,
        },
    }


def test_ping_command_sends_reply(client):
    _clear_outbox()
    r = client.post("/telegram/webhook", json=_tg_update("/ping"))
    assert r.status_code == 200
    ob = _outbox()
    assert len(ob) >= 1, "Expected a reply in telegram outbox"
    assert any("pong" in m.lower() for m in ob)


def test_help_command_lists_commands(client):
    _clear_outbox()
    r = client.post("/telegram/webhook", json=_tg_update("/help"))
    assert r.status_code == 200
    ob = _outbox()
    assert len(ob) >= 1
    assert any("/watchlist" in m for m in ob)


def test_unknown_command_is_graceful(client):
    _clear_outbox()
    r = client.post("/telegram/webhook", json=_tg_update("/not_a_real_cmd"))
    assert r.status_code == 200
    ob = _outbox()
    assert len(ob) >= 1
    assert any("help" in m.lower() or "unknown" in m.lower() for m in ob)
