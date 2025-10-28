# tests/unit/test_market_alpaca_client.py
from __future__ import annotations

import pytest

from app.adapters.market.alpaca_client import (
    AlpacaAuthError,
    AlpacaMarketClient,
)
from app.utils import env as ENV


def test_headers_include_auth_and_json(monkeypatch):
    monkeypatch.setattr(ENV, "HTTP_USER_AGENT", "unit-test-agent", raising=False)

    client = AlpacaMarketClient(
        api_key="KEY",
        api_secret="SECRET",
        timeout=3,
        retries=0,
        backoff=0.1,
        transport=lambda *args, **kwargs: (200, {}),
    )

    headers = client._build_headers()

    assert headers["APCA-API-KEY-ID"] == "KEY"
    assert headers["APCA-API-SECRET-KEY"] == "SECRET"
    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/json"
    assert headers["User-Agent"] == "unit-test-agent"


def test_snapshots_feed_mapping(monkeypatch):
    captured = {}

    def fake_transport(method, url, params=None, headers=None, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return 200, {"snapshots": {}}

    client = AlpacaMarketClient(
        api_key="KEY",
        api_secret="SECRET",
        default_feed="iex",
        timeout=3,
        retries=0,
        backoff=0.1,
        transport=fake_transport,
    )

    status, data = client.snapshots(["aapl", "MSFT", "aapl"], feed="SIP")

    assert status == 200
    assert data == {}
    assert captured["method"] == "GET"
    assert captured["params"]["feed"] == "sip"
    assert captured["params"]["symbols"] == "AAPL,MSFT"


def test_auth_error_retry_and_flag(monkeypatch):
    calls = []

    def fake_transport(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return 401, {"message": "unauthorized"}

    client = AlpacaMarketClient(
        api_key="KEY",
        api_secret="SECRET",
        timeout=1,
        retries=0,
        backoff=0.1,
        force_yahoo_on_auth_error=True,
        transport=fake_transport,
    )

    with pytest.raises(AlpacaAuthError) as exc:
        client.snapshots(["AAPL"])

    assert exc.value.fallback_to_yahoo is True
    assert len(calls) == 2
