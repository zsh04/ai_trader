from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.dal.vendors.base import FetchRequest
from app.dal.vendors.market_data import alphavantage_daily as module
from app.dal.vendors.market_data.alphavantage_daily import AlphaVantageDailyVendor


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "get_market_data_settings",
        lambda: SimpleNamespace(alphavantage_key="demo-key"),
    )


def test_fetch_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_http_get(url, params):
        return 200, {
            "Time Series (Daily)": {
                "2024-01-03": {
                    "1. open": "10.0",
                    "2. high": "11.0",
                    "3. low": "9.5",
                    "4. close": "10.5",
                    "6. volume": "1000",
                }
            }
        }

    monkeypatch.setattr(module, "http_get", fake_http_get)

    vendor = AlphaVantageDailyVendor()
    bars = vendor.fetch_bars(
        FetchRequest(
            symbol="AAPL",
            start=None,
            end=None,
            interval="1Day",
            limit=1,
        )
    )
    assert len(bars.data) == 1
    assert bars.data[0].close == pytest.approx(10.5)


def test_rejects_non_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "http_get", lambda *_: (200, {}))
    vendor = AlphaVantageDailyVendor()
    with pytest.raises(ValueError):
        vendor.fetch_bars(
            FetchRequest(
                symbol="AAPL",
                start=None,
                end=None,
                interval="60Min",
                limit=1,
            )
        )
