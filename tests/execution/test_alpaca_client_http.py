from __future__ import annotations

import importlib
from typing import Any, Dict, List


def _reload_env_and_module(monkeypatch, *, timeout="20", retries="3", backoff="2.5"):
    monkeypatch.setenv("HTTP_TIMEOUT", timeout)
    monkeypatch.setenv("HTTP_RETRIES", retries)
    monkeypatch.setenv("HTTP_BACKOFF", backoff)
    import app.utils.env as env_module

    env = importlib.reload(env_module)

    import app.execution.alpaca_client as alpaca_module

    module = importlib.reload(alpaca_module)
    return env, module


def test_alpaca_client_uses_env_defaults(monkeypatch):
    _env, alpaca_module = _reload_env_and_module(
        monkeypatch, timeout="25", retries="4", backoff="3.0"
    )

    calls: List[Dict[str, Any]] = []
    responses: List[Any] = [
        alpaca_module.requests.RequestException("boom"),
        type(
            "Resp",
            (),
            {
                "status_code": 200,
                "headers": {},
                "json": lambda self: {"ok": True},
                "text": "",
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

    monkeypatch.setattr(alpaca_module.requests, "request", fake_request)
    monkeypatch.setattr(alpaca_module, "compute_backoff_delay", fake_backoff)
    monkeypatch.setattr(alpaca_module.time, "sleep", lambda *_: None)

    client = alpaca_module.AlpacaClient(
        "key", "secret", "https://example.com", data_url="https://example.com/data"
    )

    assert client.timeout == 25.0
    assert client.retries == 4
    assert client.backoff == 3.0

    resp = client._request("GET", "https://example.com/test")
    assert resp.status_code == 200

    assert len(delays) == 1
    assert delays[0] == (0, 3.0, None)
    assert calls[0]["timeout"] == 25.0
