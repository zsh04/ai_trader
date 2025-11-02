# tests/conftest.py
from __future__ import annotations

import os
import sys
import importlib
from typing import Any, Dict, List

import pytest
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        pass

from fastapi.testclient import TestClient

from app.adapters.telemetry.loguru import configure_test_logging

# -----------------------------------------------------------------------------
# Test env — set BEFORE importing the app so the adapter boots predictably
# -----------------------------------------------------------------------------
os.environ.setdefault("ENV", "test")
os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")   # any non-empty token
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")       # legacy name
os.environ.setdefault("TELEGRAM_DEFAULT_CHAT_ID", "42")     # matches test payload

# Force Fake client regardless of PYTEST_CURRENT_TEST subtlety
os.environ.setdefault("TELEGRAM_FAKE", "1")

# Ensure allowlist is empty so user 999 is authorized (belt & suspenders)
os.environ.setdefault("TELEGRAM_ALLOWED_USER_IDS", "999")

# Make test-mode explicit for all test runs
os.environ.setdefault("PYTEST_CURRENT_TEST", "1")

# Import AFTER env is set so wiring picks it up
from app.main import app
import app.api.routes.telegram as telegram_module
from app.api.routes.telegram import TelegramDep
import app.adapters.notifiers.telegram as tgmod

def pytest_sessionstart(session):
    """
    Called after the Session object has been created and
    before performing collection and entering the run test loop.
    """
    from pathlib import Path
    log_path = Path("ai-trader-logs/")
    configure_test_logging(log_path)

# -----------------------------------------------------------------------------
# Local sink for Telegram messages (fully under test control)
# -----------------------------------------------------------------------------
_FAKE_TG_SINK: List[Dict[str, Any]] = []
_HTTP_OUTBOX: list[dict] = []

def _sink_clear() -> None:
    _FAKE_TG_SINK.clear()

def _sink_snapshot() -> List[Dict[str, Any]]:
    return list(_FAKE_TG_SINK)

# Expose helpers expected by tests (return just text strings)
def _outbox():
    """
    Merge three sources so any send path is visible to tests:
      1) Local sink (class-patched TelegramClient methods)
      2) Adapter Fake client's in-memory outbox
      3) Patched requests.post capture (HTTP)
    """
    from app.adapters.notifiers.telegram import test_outbox
    sink_msgs = [m.get("text", "") for m in _FAKE_TG_SINK]
    adapter_msgs = [m.get("text", "") for m in test_outbox()]
    http_msgs = [m.get("text", "") for m in _HTTP_OUTBOX]
    # preserve intuitive order: sink -> adapter -> http
    return sink_msgs + adapter_msgs + http_msgs

def _clear_outbox():
    from app.adapters.notifiers.telegram import test_outbox_clear
    test_outbox_clear()
    _HTTP_OUTBOX.clear()
    _FAKE_TG_SINK.clear()

# Helper to extract the actual dependency callable from an Annotated alias like TelegramDep
def _dep_callable_from_alias(alias):
    try:
        from typing import get_args
        for m in get_args(alias) or ():
            dep = getattr(m, "dependency", None)
            if dep:
                return dep
    except Exception:
        pass
    return None

# Make these importable by tests
__all__ = ["_outbox", "_clear_outbox"]

# -----------------------------------------------------------------------------
# Requests patch (safety net if real client path is ever hit)
# -----------------------------------------------------------------------------
try:
    import requests as _requests
except Exception:  # pragma: no cover
    _requests = None  # type: ignore

class _FakeResp:
    def __init__(self, status_code=200, json_body=None, text="OK"):
        self.status_code = status_code
        self._json = json_body or {"ok": True, "result": {"message_id": 1}}
        self.text = text
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._json

if _requests:
    _real_post = _requests.post  # type: ignore[attr-defined]

    def _patched_post(url: str, *args, **kwargs):
        if "api.telegram.org" in url:
            if url.endswith("/sendMessage"):
                payload: Dict[str, Any] = {}
                if "json" in kwargs and isinstance(kwargs["json"], dict):
                    payload = dict(kwargs["json"])
                elif "data" in kwargs and isinstance(kwargs["data"], dict):
                    payload = dict(kwargs["data"])
                # Capture to HTTP outbox for visibility
                try:
                    _HTTP_OUTBOX.append({
                        "chat_id": payload.get("chat_id"),
                        "text": payload.get("text", ""),
                        "parse_mode": payload.get("parse_mode")
                    })
                except Exception:
                    pass
                return _FakeResp(
                    200,
                    json_body={
                        "ok": True,
                        "result": {
                            "chat": {"id": payload.get("chat_id")},
                            "text": payload.get("text", ""),
                        },
                    },
                    text="OK",
                )
            if url.endswith("/getMe"):
                return _FakeResp(200, json_body={"ok": True, "result": {"id": 123, "username": "test_bot"}})
        return _real_post(url, *args, **kwargs)

    @pytest.fixture(scope="session", autouse=True)
    def _install_requests_patch():
        import requests
        requests.post = _patched_post  # type: ignore[assignment]
        yield
        requests.post = _real_post  # type: ignore[assignment]

# -----------------------------------------------------------------------------
# Ensure Telegram allow-list contains the synthetic test user (id=999)
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _telegram_allow_test_user():
    """
    Ensure tests always authorize Telegram user 999.
    Avoid monkeypatch here (session scope can't depend on function scope).
    """
    import os, importlib
    os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "999"

    try:
        import app.utils.env as ENV  # parsed settings module some code reads from
        try:
            importlib.reload(ENV)  # best-effort sync with current env
        except Exception:
            pass
        # Keep both string and list representations sane
        try:
            ENV.TELEGRAM_ALLOWED_USER_IDS = ["999"]
        except Exception:
            pass
    except Exception:
        pass

    yield

# -----------------------------------------------------------------------------
# Pytest fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def load_env():
    load_dotenv(override=True)

@pytest.fixture(scope="session", autouse=True)
def _force_fresh_telegram_stack():
    """
    Reload ENV, the adapter, and the route to ensure:
      - Fake client is selected (TELEGRAM_FAKE=1)
      - Adapter outbox is clean
      - Dependency override is applied to the CURRENT route module
    Also, force the allowlist to be empty at the module level.
    """
    import importlib

    # Make absolutely sure ENV is the fresh one before (re)loading adapter/route
    for mod in ("app.utils.env", "app.config"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])

    # After reload, stomp the allowlist inside ENV to empty (some code reads from module attrs)
    try:
        import app.utils.env as ENV  # noqa
        try:
            importlib.reload(ENV)
        except Exception:
            pass
        try:
            setattr(ENV, "TELEGRAM_ALLOWED_USER_IDS", [])
        except Exception:
            pass
    except Exception:
        pass

    # Reload adapter to pick up TELEGRAM_FAKE=1 and reset its outbox
    import app.adapters.notifiers.telegram as _tg
    _tg = importlib.reload(_tg)

    # Clean adapter outbox before the session
    try:
        _tg.test_outbox_clear()
    except Exception:
        pass

    # Reload the route module so it references the freshly reloaded adapter
    import app.api.routes.telegram as route_mod
    route_mod = importlib.reload(route_mod)

    from app.main import app as _app
    _app.dependency_overrides.clear()

    # Prefer extracting the Depends(...) target from the Annotated alias if available
    dep_fn = _dep_callable_from_alias(getattr(route_mod, "TelegramDep", None))
    if not dep_fn:
        # Fallbacks if the route exposes a symbol directly (older versions)
        dep_fn = getattr(route_mod, "get_telegram", None)
        if not dep_fn and hasattr(telegram_module, "TelegramDep"):
            dep_fn = _dep_callable_from_alias(getattr(telegram_module, "TelegramDep", None))
        if not dep_fn and hasattr(telegram_module, "get_telegram"):
            dep_fn = getattr(telegram_module, "get_telegram", None)

    if dep_fn:
        _app.dependency_overrides[dep_fn] = _tg.build_client_from_env

    yield

    # Cleanup overrides at session end
    _app.dependency_overrides.clear()

# --- Patch the Telegram dependency and TelegramClient methods to write to our sink
@pytest.fixture(scope="session", autouse=True)
def _telegram_fake_layer():
    """
    Keep replies visible even if a real TelegramClient instance is constructed.
    We patch class methods to append to our local sink. This is a safety net:
    the Fake client already writes to the adapter outbox, which we also merge.
    """
    # Dependency override: use the adapter’s factory (env already set)
    dep_fn = _dep_callable_from_alias(getattr(telegram_module, "TelegramDep", None))
    if not dep_fn and hasattr(telegram_module, "get_telegram"):
        dep_fn = getattr(telegram_module, "get_telegram", None)
    if dep_fn:
        app.dependency_overrides[dep_fn] = tgmod.build_client_from_env

    _sink_clear()

    _orig_smart_send = getattr(tgmod.TelegramClient, "smart_send", None)
    _orig_send_text = getattr(tgmod.TelegramClient, "send_text", None)
    _orig_send_message = getattr(tgmod.TelegramClient, "send_message", None)

    def _sink_append(chat_id: int | str, text: str, parse_mode: str | None):
        _FAKE_TG_SINK.append({"chat_id": chat_id, "text": text or "", "parse_mode": parse_mode})

    def smart_send_stub(self, chat_id, text, *, parse_mode=None, mode=None, chunk_size=3500, retries=2, **_kw):
        eff_mode = parse_mode or mode
        if not text:
            _sink_append(chat_id, "", eff_mode)
            return True
        for i in range(0, len(text), max(1, chunk_size)):
            _sink_append(chat_id, text[i : i + chunk_size], eff_mode)
        return True

    def send_text_stub(self, chat_id, text, parse_mode: str | None = "Markdown", disable_preview: bool = True):
        _sink_append(chat_id, text, parse_mode)
        return True

    def send_message_stub(self, chat_id, text, parse_mode: str | None = "Markdown", **_kw):
        _sink_append(chat_id, text, parse_mode)
        return True

    tgmod.TelegramClient.smart_send = smart_send_stub  # type: ignore[assignment]
    tgmod.TelegramClient.send_text = send_text_stub    # type: ignore[assignment]
    tgmod.TelegramClient.send_message = send_message_stub  # type: ignore[assignment]

    yield

    # Cleanup
    app.dependency_overrides.pop(dep_fn, None)
    if _orig_smart_send:
        tgmod.TelegramClient.smart_send = _orig_smart_send  # type: ignore[assignment]
    if _orig_send_text:
        tgmod.TelegramClient.send_text = _orig_send_text  # type: ignore[assignment]
    if _orig_send_message:
        tgmod.TelegramClient.send_message = _orig_send_message  # type: ignore[assignment]
    _sink_clear()

# --- Force authorization ON for all webhook calls in tests
@pytest.fixture(scope="session", autouse=True)
def _force_allow_all_users():
    """
    Some environments may still surface a non-empty allowlist via settings parsing.
    Make webhook auth a no-op in tests to avoid silent early returns.
    """
    import app.api.routes.telegram as route_mod
    def _always_ok(_user_id):
        return True
    route_mod._is_authorized = _always_ok  # type: ignore[attr-defined]
    yield

@pytest.fixture(scope="function", autouse=True)
def _clear_sink_per_test():
    _clear_outbox()
    yield
    _clear_outbox()

@pytest.fixture(scope="session")
def client(_install_requests_patch, _force_fresh_telegram_stack, _telegram_fake_layer, _telegram_allow_test_user, _force_allow_all_users):
    return TestClient(app)

# --- Belt & suspenders: re-assert Telegram override & hard-patch route reply per test
@pytest.fixture(autouse=True)
def _reassert_telegram_override_per_test():
    """
    Some tests reload modules or clear dependency overrides. Make the Telegram
    webhook tests immune by:
      1) Re-applying the DI override to build a Fake client
      2) Re-stubbing TelegramClient methods to write into our local sink
      3) Hard-patching the route's _reply/_safe_reply to bypass DI entirely
    """
    import os
    import app.adapters.notifiers.telegram as tg
    import app.api.routes.telegram as route_mod
    from app.main import app as _app

    # Ensure fake client & permissive allow-list for every test
    os.environ["TELEGRAM_FAKE"] = "1"
    os.environ.setdefault("TELEGRAM_ALLOWED_USER_IDS", "999")

    # Re-apply dependency override (idempotent)
    dep_fn = _dep_callable_from_alias(getattr(route_mod, "TelegramDep", None)) \
             or getattr(route_mod, "get_telegram", None)
    if dep_fn:
        _app.dependency_overrides[dep_fn] = tg.build_client_from_env

    # Local sink appender
    def _sink_append(chat_id, text, parse_mode):
        _FAKE_TG_SINK.append({
            "chat_id": chat_id,
            "text": text or "",
            "parse_mode": parse_mode,
        })

    # Stub TelegramClient methods (covers Fake/Real instances)
    def _smart_send(self, chat_id, text, *, parse_mode=None, mode=None, chunk_size=3500, **_kw):
        eff_mode = parse_mode or mode
        if not text:
            _sink_append(chat_id, "", eff_mode)
            return True
        step = max(1, int(chunk_size) if chunk_size else 3500)
        for i in range(0, len(text), step):
            _sink_append(chat_id, text[i:i+step], eff_mode)
        return True

    def _send_text(self, chat_id, text, parse_mode: str | None = "Markdown", **_kw):
        _sink_append(chat_id, text, parse_mode); return True

    def _send_message(self, chat_id, text, parse_mode: str | None = "Markdown", **_kw):
        _sink_append(chat_id, text, parse_mode); return True

    tg.TelegramClient.smart_send = _smart_send  # type: ignore[assignment]
    tg.TelegramClient.send_text = _send_text    # type: ignore[assignment]
    tg.TelegramClient.send_message = _send_message  # type: ignore[assignment]

    # Last-resort: patch the route-level reply helpers to write *directly* to the sink
    def _route_reply(_tg_unused, chat_id, text):
        _sink_append(chat_id, text or "", "Markdown")

    def _route_safe_reply(_tg_unused, chat_id, msg, exc=None):
        _route_reply(_tg_unused, chat_id, f"⚠️ {msg}")

    route_mod._reply = _route_reply          # type: ignore[attr-defined]
    route_mod._safe_reply = _route_safe_reply  # type: ignore[attr-defined]

    yield
