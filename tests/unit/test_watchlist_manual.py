from __future__ import annotations

import pytest

from app.domain.watchlist_service import resolve_watchlist


@pytest.fixture(autouse=True)
def _clear_warned_keys():
    # ensure warn-once cache doesn't leak between tests
    from app.domain import watchlist_service

    watchlist_service._WARNED_KEYS.clear()
    yield
    watchlist_service._WARNED_KEYS.clear()


def _set_env(monkeypatch, **values):
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_manual_watchlist_basic(monkeypatch):
    _set_env(
        monkeypatch,
        WATCHLIST_SOURCE="manual",
        WATCHLIST_TEXT="AAPL, msft, NVDA",
        MAX_WATCHLIST="5",
    )

    source, symbols = resolve_watchlist()
    assert source == "manual"
    assert symbols == ["AAPL", "MSFT", "NVDA"]


def test_manual_watchlist_respects_max(monkeypatch):
    _set_env(
        monkeypatch,
        WATCHLIST_SOURCE="manual",
        WATCHLIST_TEXT="AAPL, MSFT, NVDA",
        MAX_WATCHLIST="2",
    )

    source, symbols = resolve_watchlist()
    assert source == "manual"
    assert symbols == ["AAPL", "MSFT"]


def test_manual_watchlist_dedupes_and_ignores_empty(monkeypatch):
    _set_env(
        monkeypatch,
        WATCHLIST_SOURCE="manual",
        WATCHLIST_TEXT="  , aapl , , AAPL , msft , MsFt ,",
        MAX_WATCHLIST="10",
    )

    source, symbols = resolve_watchlist()
    assert source == "manual"
    assert symbols == ["AAPL", "MSFT"]
