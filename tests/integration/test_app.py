from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from app.wiring import TelegramDep as WiringTelegramDep, get_telegram as wiring_get_telegram
from app.wiring import router as wiring_router

load_dotenv(override=True)
os.environ.setdefault("TELEGRAM_ALLOW_TEST_NO_SECRET", "1")


def make_client(monkeypatch):
    import sys
    import types

    fake_db = types.ModuleType("app.adapters.db.postgres")

    class DummyEngine:
        def begin(self):
            from contextlib import contextmanager

            @contextmanager
            def cm():
                class Conn:
                    def execute(self, *_args, **_kwargs):
                        return None

                yield Conn()

            return cm()

    fake_db.make_engine = lambda: DummyEngine()
    fake_db.ping = lambda retries=1: True
    sys.modules["app.adapters.db.postgres"] = fake_db
    sys.modules.setdefault("app.adapters.db", types.ModuleType("app.adapters.db"))
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = types.SimpleNamespace(debug=lambda *_, **__: None)
    sys.modules["loguru"] = fake_loguru

    fake_notifier = types.ModuleType("app.adapters.notifiers.telegram_notifier")
    fake_notifier.TelegramNotifier = object
    sys.modules["app.adapters.notifiers.telegram_notifier"] = fake_notifier

    import app.main as main_module

    class FakeTelegram:
        def smart_send(self, chat_id, text, **kwargs):
            pass

        def send_text(self, chat_id, text):
            pass

    fake_dep = lambda: FakeTelegram()

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    client = TestClient(main_module.app)

    # Robust dependency overrides: work whether main re-exports TelegramDep or not
    main_dep = getattr(main_module, "TelegramDep", None)
    if main_dep is not None:
        client.app.dependency_overrides[main_dep] = fake_dep

    # Always override wiring deps used by the router
    client.app.dependency_overrides[WiringTelegramDep] = fake_dep
    client.app.dependency_overrides[wiring_get_telegram] = fake_dep

    return client


def test_health_live(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True


def test_telegram_webhook_ping(monkeypatch):
    client = make_client(monkeypatch)

    payload = {"message": {"chat": {"id": 1}, "text": "/ping"}}
    # secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    response = client.post(
        "/telegram/webhook",
        json=payload,
        headers={
            "X-Telegram-Bot-Api-Secret-Token": os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
        },
    )

    assert response.status_code == 200, response.text
