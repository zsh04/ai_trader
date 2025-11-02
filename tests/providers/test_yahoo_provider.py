from __future__ import annotations

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
    logger.remove()
    logger.add(caplog.handler, level="WARNING")

    data = yahoo_provider._fetch_chart_history("AAPL", "2024-01-01", "2024-01-10")

    assert data == {}
    assert "period1" in captured["params"]
    assert captured["kwargs"]["retries"] == ENV.HTTP_RETRIES
    assert captured["kwargs"]["backoff"] == ENV.HTTP_BACKOFF
    assert captured["kwargs"]["timeout"] == ENV.HTTP_TIMEOUT

    assert any("yahoo history fetch failed" in rec.message for rec in caplog.records)
    record = caplog.records[0]
    assert record.extra["provider"] == "yahoo"
    assert record.extra["status"] == 500
