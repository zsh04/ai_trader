# tests/conftest.py
from __future__ import annotations
import os
import sys
import importlib
import json
import requests as _requests
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from typing import Any, Dict

# Ensure dev-like behavior for webhook
os.environ.setdefault("ENV", "dev")
os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_DEFAULT_CHAT_ID", "42")  # <- match your test payload

from app.main import app
from app.api.routes.telegram import TelegramDep
import app.api.routes.telegram as telegram_module  # we'll spy on _reply()

# -------- Shared outbox ----------
_SENT: list[Dict[str, Any]] = []

def _outbox() -> list[dict]:
    # return a copy so tests can't mutate our store inadvertently
    return list(_SENT)

def _clear_outbox() -> None:
    _SENT.clear()

class _FakeResp:
    def __init__(self, status_code=200, json_body=None, text="OK"):
        self.status_code = status_code
        self._json = json_body or {"ok": True, "result": {"message_id": 1}}
        self.text = text
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._json

_real_post = _requests.post

def _patched_post(url: str, *args, **kwargs):
    # Only intercept Telegram send endpoints; passthrough everything else
    if "api.telegram.org" in url and url.endswith("/sendMessage"):
        # capture both json and form payloads
        payload: Dict[str, Any] = {}
        if "json" in kwargs and isinstance(kwargs["json"], dict):
            payload = dict(kwargs["json"])
        elif "data" in kwargs and isinstance(kwargs["data"], dict):
            payload = dict(kwargs["data"])
        # pretend success
        return _FakeResp(
            200,
            json_body={"ok": True, "result": {"chat": {"id": payload.get("chat_id")}, "text": payload.get("text", "")}},
            text="OK",
        )
    # allow getMe and others to succeed as well
    if "api.telegram.org" in url and url.endswith("/getMe"):
        return _FakeResp(200, json_body={"ok": True, "result": {"id": 123, "username": "test_bot"}})
    return _real_post(url, *args, **kwargs)

@pytest.fixture(scope="session", autouse=True)
def _install_requests_patch():
    import requests
    requests.post = _patched_post  # type: ignore[assignment]
    yield
    requests.post = _real_post  # type: ignore[assignment]

# -------- Fake client (still override the dep so no real HTTP happens) --------
class _FakeTelegram:
    def send_message(self, chat_id, text, **kw):
        # record outbound messages for assertions
        try:
            cid = int(str(chat_id))
        except Exception:
            cid = chat_id
        _SENT.append({"chat_id": cid, "text": str(text), "kwargs": dict(kw)})
        return {"ok": True}

    def smart_send(self, chat_id, text, **kw):
        # mirror real client by delegating to send_message
        return self.send_message(chat_id, text, **kw)

_FAKE = _FakeTelegram()

@pytest.fixture(scope="session", autouse=True)
def load_env():
    load_dotenv(override=True)

@pytest.fixture(scope="session", autouse=True)
def _reload_env_modules():
    for mod in ("app.config",):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    yield

@pytest.fixture(scope="session", autouse=True)
def _override_telegram_dep():
    app.dependency_overrides[TelegramDep] = lambda: _FAKE
    yield
    app.dependency_overrides.pop(TelegramDep, None)

@pytest.fixture(scope="session", autouse=True)
def _spy_reply():
    # Wrap the route-level reply function so we ALWAYS record outbound texts
    orig = telegram_module._reply

    def spy(tg, chat_id, text):
        return orig(tg, chat_id, text)

    telegram_module._reply = spy
    yield
    telegram_module._reply = orig

@pytest.fixture(scope="session")
def client():
    return TestClient(app)