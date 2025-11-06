from __future__ import annotations

import importlib
import types

from loguru import logger

from app.providers import yahoo_provider
from app.utils import env as ENV


def test_fetch_chart_history_non_200(monkeypatch, caplog):
    captured: dict = {}

    def fake_http_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        captured["kwargs"] = kwargs
        return 500, {"chart": {"error": "nope"}}

    monkeypatch.setattr(yahoo_provider, "http_get", fake_http_get)
    handler_id = logger.add(caplog.handler, level="WARNING")

    try:
        data = yahoo_provider._fetch_chart_history("AAPL", "2024-01-01", "2024-01-10")

        assert data == {}
        assert "period1" in captured["params"]
        assert captured["kwargs"]["retries"] == ENV.HTTP_RETRIES
        assert captured["kwargs"]["backoff"] == ENV.HTTP_BACKOFF
        assert captured["kwargs"]["timeout"] == ENV.HTTP_TIMEOUT

        assert any(
            "yahoo history fetch failed" in rec.message for rec in caplog.records
        )
        record = caplog.records[0]
        assert getattr(record, "provider", None) == "yahoo"
        assert getattr(record, "status", None) == 500
    finally:
        logger.remove(handler_id)


def test_yahoo_request_uses_env(monkeypatch):
    monkeypatch.setenv("HTTP_TIMEOUT", "12")
    monkeypatch.setenv("HTTP_RETRIES", "2")
    monkeypatch.setenv("HTTP_BACKOFF", "1.7")

    import app.utils.env as env_module

    importlib.reload(env_module)

    import app.providers.yahoo_provider as module

    module = importlib.reload(module)

    calls = []
    outcomes = [
        module.requests.RequestException("boom"),
        type(
            "Resp429",
            (),
            {
                "status_code": 429,
                "headers": {"Retry-After": "1"},
                "text": "Edge: Too Many Requests",
                "json": lambda self: {},
            },
        )(),
        type(
            "RespOk",
            (),
            {
                "status_code": 200,
                "headers": {},
                "text": "",
                "json": lambda self: {"chart": {"result": True}},
            },
        )(),
    ]

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    delays = []

    def fake_backoff(attempt, backoff, retry_after):
        delays.append((attempt, backoff, retry_after))
        return 0.0

    if not hasattr(module.logger, "warning"):
        module.logger = types.SimpleNamespace(
            warning=lambda *_, **__: None,
            debug=lambda *_, **__: None,
            info=lambda *_, **__: None,
            error=lambda *_, **__: None,
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module, "compute_backoff_delay", fake_backoff)
    monkeypatch.setattr(module.time, "sleep", lambda *_: None)

    status, data = module._yahoo_request("https://example.com")
    assert status == 200
    assert data == {"chart": {"result": True}}

    assert len(calls) == 3
    assert calls[0]["timeout"] == 12.0
    assert len(delays) == 2
    assert delays[0] == (0, 1.7, None)
    assert delays[1] == (1, 1.7, "1")
