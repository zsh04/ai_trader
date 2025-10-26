from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.utils import http


class DummyResponse:
    def __init__(self, status: int, payload: Dict[str, Any], headers: Dict[str, Any] | None = None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._payload


class DummyRequests:
    def __init__(self, responses: List[DummyResponse]):
        self.responses = responses
        self.calls: List[Dict[str, Any]] = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_http_get_retries_and_backoff(monkeypatch, caplog):
    responses = [
        DummyResponse(500, {"error": "boom"}),
        DummyResponse(200, {"ok": True}),
    ]
    fake_requests = DummyRequests(responses)
    monkeypatch.setattr(http, "requests", fake_requests)
    monkeypatch.setattr(http.random, "uniform", lambda *_: 1.0)

    sleeps: List[float] = []
    monkeypatch.setattr(http.time, "sleep", lambda s: sleeps.append(s))
    perf_values = iter([0.0, 0.01, 1.0, 1.05])
    monkeypatch.setattr(http.time, "perf_counter", lambda: next(perf_values))

    caplog.set_level(logging.INFO)

    status, data = http.http_get("https://example.com/api")

    assert status == 200
    assert data == {"ok": True}
    assert len(fake_requests.calls) == 2
    assert sleeps == [1.5]
    assert any("method=GET url=https://example.com/api status=500" in record.message for record in caplog.records)
