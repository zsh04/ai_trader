from __future__ import annotations
import os
from fastapi.testclient import TestClient
from dotenv import load_dotenv

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
    import app.wiring.telegram as telegram_module
    import app.wiring.telegram_router as router_module

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    client = TestClient(main_module.app)
    client.app.dependency_overrides[main_module.TelegramDep] = fake_dep
    client.app.dependency_overrides[telegram_module.TelegramDep] = fake_dep
    client.app.dependency_overrides[router_module.TelegramDep] = fake_dep
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
    #secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    response = client.post(
        "/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": os.getenv("TELEGRAM_WEBHOOK_SECRET", "")},
    )

    assert response.status_code == 200, response.text
