from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.dal.vendors.base import FetchRequest
from app.dal.vendors.market_data import finnhub as module
from app.dal.vendors.market_data.finnhub import FinnhubVendor


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "get_market_data_settings",
        lambda: SimpleNamespace(finnhub_key="demo-key"),
    )


def test_daily_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_http_get(url, params):
        assert url.endswith("/quote")
        return 200, {
            "c": 10.5,
            "h": 11.0,
            "l": 9.5,
            "o": 10.0,
            "pc": 9.9,
            "t": 1_700_000_000,
        }

    monkeypatch.setattr(module, "http_get", fake_http_get)

    vendor = FinnhubVendor()
    start = datetime.now(timezone.utc) - timedelta(days=2)
    end = datetime.now(timezone.utc)
    bars = vendor.fetch_bars(
        FetchRequest(
            symbol="AAPL",
            start=start,
            end=end,
            interval="1Day",
            limit=5,
        )
    )

    assert len(bars.data) == 1
    bar = bars.data[0]
    assert bar.close == pytest.approx(10.5)
    assert bar.open == pytest.approx(10.0)
    assert bar.source == "daily_quote"
