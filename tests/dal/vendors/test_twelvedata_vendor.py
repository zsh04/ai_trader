from __future__ import annotations

from datetime import datetime, timezone

from app.dal.vendors.base import FetchRequest
from app.dal.vendors.market_data import twelvedata as td_module
from app.dal.vendors.market_data.twelvedata import TwelveDataVendor


def test_fetch_bars_without_api_key(monkeypatch):
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    
    # ENV is a frozen dataclass instantiated at import time, so it caches the API key.
    # We must replace the module-level ENV with a fresh one that sees the deleted env var.
    from app.utils.env import EnvSettings
    monkeypatch.setattr(td_module, "ENV", EnvSettings())

    vendor = TwelveDataVendor(api_key="")
    request = FetchRequest(
        symbol="AAPL",
        start=None,
        end=None,
        interval="1Day",
        limit=5,
    )

    bars = vendor.fetch_bars(request)
    assert bars.symbol == "AAPL"
    assert bars.vendor == "twelvedata"
    assert bars.data == []


def test_fetch_bars_parses_payload(monkeypatch):
    monkeypatch.setenv("TWELVEDATA_API_KEY", "sample-key")

    def fake_http_get(url, params=None, **kwargs):  # noqa: D401
        return 200, {
            "values": [
                {
                    "datetime": "2024-01-02 15:31:00",
                    "open": "100.6",
                    "high": "101.2",
                    "low": "100.2",
                    "close": "101",
                    "volume": "1500",
                },
                {
                    "datetime": "2024-01-02 15:30:00",
                    "open": "100",
                    "high": "101",
                    "low": "99",
                    "close": "100.5",
                    "volume": "1234",
                },
            ]
        }

    monkeypatch.setattr(td_module, "http_get", fake_http_get)

    vendor = TwelveDataVendor()
    request = FetchRequest(
        symbol="MSFT",
        start=datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 16, 0, tzinfo=timezone.utc),
        interval="1Min",
        limit=2,
    )

    bars = vendor.fetch_bars(request)
    records = bars.data
    assert len(records) == 2
    assert records[0].timestamp < records[1].timestamp
    assert records[-1].close == 101.0
    assert records[-1].volume == 1500
