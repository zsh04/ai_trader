from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.dal.vendors.base import FetchRequest
from app.dal.vendors.market_data import alphavantage as module
from app.dal.vendors.market_data.alphavantage import AlphaVantageVendor


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "get_market_data_settings",
        lambda: SimpleNamespace(alphavantage_key="demo-key"),
    )


def test_fetch_bars_normalizes_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_params = {}

    def fake_http_get(url, params):
        captured_params.update(params)
        return 200, {
            "Time Series (1min)": {
                "2024-01-01 10:00:00": {
                    "1. open": "1.0",
                    "2. high": "1.5",
                    "3. low": "0.9",
                    "4. close": "1.2",
                    "5. volume": "100",
                }
            }
        }

    monkeypatch.setattr(module, "http_get", fake_http_get)

    vendor = AlphaVantageVendor()
    bars = vendor.fetch_bars(
        FetchRequest(
            symbol="AAPL",
            start=None,
            end=None,
            interval="1Min",
            limit=1,
        )
    )

    assert captured_params["interval"] == "1min"
    assert len(bars.data) == 1
    assert bars.data[0].close == pytest.approx(1.2)


def test_fetch_bars_rejects_daily_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "http_get", lambda *_: (200, {}))
    vendor = AlphaVantageVendor()
    with pytest.raises(ValueError):
        vendor.fetch_bars(
            FetchRequest(
                symbol="AAPL",
                start=None,
                end=None,
                interval="1Day",
                limit=1,
            )
        )
