from __future__ import annotations

import importlib
from typing import Any, Dict, List


def _reload_telegram(monkeypatch):
    monkeypatch.setenv("HTTP_TIMEOUT", "11")
    monkeypatch.setenv("HTTP_RETRIES", "2")
    monkeypatch.setenv("HTTP_BACKOFF", "1.1")
    monkeypatch.setenv("TELEGRAM_TIMEOUT_SECS", "9")
    import app.utils.env as env_module

    importlib.reload(env_module)

    import app.adapters.notifiers.telegram as telegram_module

    return importlib.reload(telegram_module)


def test_telegram_request_applies_env(monkeypatch):
    telegram_module = _reload_telegram(monkeypatch)

    calls: List[Dict[str, Any]] = []
    responses: List[Any] = [
        telegram_module.requests.RequestException("boom"),
        type(
            "Resp429",
            (),
            {
                "status_code": 429,
                "headers": {"Retry-After": "1"},
                "text": "Edge: Too Many Requests",
                "json": lambda self: {"ok": False},
            },
        )(),
        type(
            "RespOk",
            (),
            {
                "status_code": 200,
                "headers": {},
                "text": "",
                "json": lambda self: {"ok": True},
            },
        )(),
    ]

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        outcome = responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    delays: List[Any] = []

    def fake_backoff(attempt, backoff, retry_after):
        delays.append((attempt, backoff, retry_after))
        return 0.0

    client = telegram_module.TelegramClient("token")

    monkeypatch.setattr(telegram_module.requests, "request", fake_request)
    monkeypatch.setattr(telegram_module, "compute_backoff_delay", fake_backoff)
    monkeypatch.setattr(telegram_module.time, "sleep", lambda *_: None)

    resp = client._request("POST", "sendMessage", json={"chat_id": 1})
    assert resp is not None
    assert resp.status_code == 200

    assert client.timeout == 9
    assert client.retries == 2
    assert client.backoff == 1.1

    assert len(delays) == 2
    assert delays[0] == (0, 1.1, None)
    assert delays[1] == (1, 1.1, "1")

    assert len(calls) == 3
    assert calls[0]["timeout"] == 9.0
