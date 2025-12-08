from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.dal.vendors.base import FetchRequest
from app.dal.vendors.market_data.marketstack import MarketstackVendor


@pytest.fixture
def mock_env_api_key(monkeypatch):
    monkeypatch.setenv("MARKETSTACK_API_KEY", "dummy_key")
    from app.dal.vendors.market_data import marketstack
    from app.utils.env import EnvSettings
    # Replace module-level ENV with a fresh instance that picks up the env var
    monkeypatch.setattr(marketstack, "ENV", EnvSettings())

def test_fetch_bars_success(mock_env_api_key, monkeypatch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 102.0,
                "volume": 1000.0,
                "adj_high": 105.0,
                "adj_low": 99.0,
                "adj_close": 102.0,
                "adj_open": 100.0,
                "adj_volume": 1000.0,
                "split_factor": 1.0,
                "dividend": 0.0,
                "symbol": "AAPL",
                "exchange": "XNAS",
                "date": "2023-01-01T00:00:00+0000"
            }
        ]
    }
    mock_resp.status_code = 200
    
    mock_requests = MagicMock()
    mock_requests.get.return_value = mock_resp
    monkeypatch.setattr("requests.get", mock_requests.get)

    vendor = MarketstackVendor()
    req = FetchRequest(symbol="AAPL", start=datetime(2023, 1, 1, tzinfo=timezone.utc), end=None, interval="1Day")
    bars = vendor.fetch_bars(req)

    assert len(bars.data) == 1
    assert bars.data[0].open == 100.0
    assert bars.data[0].close == 102.0
    assert bars.vendor == "marketstack"

def test_fetch_bars_no_key(monkeypatch):
    # Ensure no key
    monkeypatch.delenv("MARKETSTACK_API_KEY", raising=False)
    from app.dal.vendors.market_data import marketstack
    from app.utils.env import EnvSettings
    monkeypatch.setattr(marketstack, "ENV", EnvSettings())
    
    vendor = MarketstackVendor(api_key="")
    req = FetchRequest(symbol="AAPL", start=None, end=None, interval="1Day")
    bars = vendor.fetch_bars(req)
    
    assert len(bars.data) == 0

def test_fetch_bars_error_response(mock_env_api_key, monkeypatch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "error": {
            "code": "rate_limit_reached",
            "message": "You have reached your monthly limit."
        }
    }
    mock_resp.status_code = 200 # Marketstack often returns 200 or 422 with error body
    
    mock_requests = MagicMock()
    mock_requests.get.return_value = mock_resp
    monkeypatch.setattr("requests.get", mock_requests.get)

    vendor = MarketstackVendor()
    req = FetchRequest(symbol="AAPL", start=None, end=None, interval="1Day")
    bars = vendor.fetch_bars(req)

    assert len(bars.data) == 0
