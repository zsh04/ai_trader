# tests/unit/test_watchlist_service.py
import os

import pytest

from app.domain import watchlist_service


@pytest.fixture(autouse=True)
def _reset_counters():
    watchlist_service._COUNTERS.clear()
    yield
    watchlist_service._COUNTERS.clear()


def test_resolve_watchlist_auto_priority(monkeypatch):
    monkeypatch.delenv("WATCHLIST_SOURCE", raising=False)
    monkeypatch.setenv("WATCHLIST_TEXT", "")
    monkeypatch.setattr(watchlist_service, "fetch_alpha_vantage_symbols", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(watchlist_service, "fetch_finnhub_symbols", lambda: [])
    monkeypatch.setattr(watchlist_service, "fetch_twelvedata_symbols", lambda: [])
    monkeypatch.setattr(watchlist_service, "build_watchlist", lambda source="textlist": [])

    source, symbols = watchlist_service.resolve_watchlist()
    assert source == "alpha"
    assert symbols == ["AAPL", "MSFT"]


def test_resolve_watchlist_auto_fallback_to_textlist(monkeypatch):
    monkeypatch.delenv("WATCHLIST_SOURCE", raising=False)
    monkeypatch.setattr(watchlist_service, "fetch_alpha_vantage_symbols", lambda: [])
    monkeypatch.setattr(watchlist_service, "fetch_finnhub_symbols", lambda: [])
    monkeypatch.setattr(watchlist_service, "fetch_twelvedata_symbols", lambda: [])
    monkeypatch.setattr(watchlist_service, "build_watchlist", lambda source="textlist": ["nvda", " tsla"])

    source, symbols = watchlist_service.resolve_watchlist()
    assert source == "textlist"
    assert symbols == ["NVDA", "TSLA"]


def test_resolve_watchlist_manual(monkeypatch):
    monkeypatch.setenv("WATCHLIST_SOURCE", "manual")
    monkeypatch.setenv("WATCHLIST_TEXT", "spy, qqq")

    source, symbols = watchlist_service.resolve_watchlist()
    assert source == "manual"
    assert symbols == ["SPY", "QQQ"]


def test_resolve_watchlist_specific_provider(monkeypatch):
    monkeypatch.setenv("WATCHLIST_SOURCE", "finnhub")
    monkeypatch.setattr(watchlist_service, "fetch_finnhub_symbols", lambda: ["oklo", "rgti"])

    source, symbols = watchlist_service.resolve_watchlist()
    assert source == "finnhub"
    assert symbols == ["OKLO", "RGTI"]
