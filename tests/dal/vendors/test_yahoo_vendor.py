from __future__ import annotations

from datetime import date

import pandas as pd
from loguru import logger

from app.dal.vendors.base import FetchRequest
from app.dal.vendors.market_data import yahoo as yahoo_module
from app.dal.vendors.market_data.yahoo import YahooVendor
from app.utils import env as ENV


def test_fetch_chart_history_non_200(monkeypatch, caplog):
    captured: dict = {}

    def fake_http_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        captured["kwargs"] = kwargs
        return 500, {"chart": {"error": "nope"}}

    monkeypatch.setattr(yahoo_module, "http_get", fake_http_get)
    handler_id = logger.add(caplog.handler, level="WARNING")

    try:
        data = yahoo_module._fetch_chart_history(
            "AAPL", date(2024, 1, 1), date(2024, 1, 2)
        )

        assert data == {}
        assert "period1" in captured["params"]
        assert captured["kwargs"]["retries"] == ENV.HTTP_RETRIES
        assert captured["kwargs"]["backoff"] == ENV.HTTP_BACKOFF
        assert captured["kwargs"]["timeout"] == ENV.HTTP_TIMEOUT

        assert any(
            "yahoo chart history failed" in rec.message for rec in caplog.records
        )
        record = caplog.records[0]
        assert getattr(record, "provider", None) == "yahoo"
        assert getattr(record, "status", None) == 500
    finally:
        logger.remove(handler_id)


def test_fetch_bars_falls_back_to_chart_api(monkeypatch):
    monkeypatch.setattr(yahoo_module, "yf", None)

    sample_df = pd.DataFrame(
        {
            "open": [100.0],
            "high": [105.0],
            "low": [99.5],
            "close": [102.5],
            "volume": [1_234_567],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-02")], name="timestamp"),
    )

    monkeypatch.setattr(
        yahoo_module,
        "_fetch_chart_history",
        lambda *_, **__: {"chart": {"result": True}},
    )
    monkeypatch.setattr(
        yahoo_module,
        "_chart_payload_to_dataframe",
        lambda *_, **__: sample_df,
    )

    vendor = YahooVendor()
    request = FetchRequest(
        symbol="AAPL",
        start=None,
        end=None,
        interval="1Day",
        limit=1,
    )
    bars = vendor.fetch_bars(request)

    assert bars.symbol == "AAPL"
    assert bars.vendor == "yahoo"
    assert len(bars.data) == 1
    bar = bars.data[0]
    assert bar.close == 102.5
    assert bar.volume == 1_234_567
