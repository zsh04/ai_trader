import os
from fastapi.testclient import TestClient
from tests.conftest import _outbox, _clear_outbox

os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")

from app.main import app  # noqa

client = TestClient(app)

def _tg_update(text: str):
    return {
        "update_id": 3001,
        "message": {
            "message_id": 333,
            "from": {"id": 999, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 7, "type": "private"},
            "date": 1700000002,
            "text": text,
        },
    }

def test_webhook_endpoint_exists():
    r = client.post("/telegram/webhook", json=_tg_update("/ping"))
    assert r.status_code == 200