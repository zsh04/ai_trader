# tests/unit/test_watchlist_service.py
import os
import sys
import types

import pytest

from app.domain import watchlist_service


def _patch_source(monkeypatch, name: str, values):
    module_name = f"app.source.{name}_source"
    stub = types.ModuleType(module_name)
    stub.get_symbols = lambda: values  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, stub)


@pytest.fixture(autouse=True)
def _reset_watchlist_service():
    watchlist_service._WARNED_KEYS.clear()
    yield
    watchlist_service._WARNED_KEYS.clear()


def test_resolve_watchlist_default_textlist(monkeypatch):
    monkeypatch.delenv("WATCHLIST_SOURCE", raising=False)
    _patch_source(monkeypatch, "textlist", [" aapl", "msft", "aapl"])

    source, symbols = watchlist_service.resolve_watchlist()
    assert source == "textlist"
    assert symbols == ["AAPL", "MSFT"]


def test_resolve_watchlist_scanner_fallback(monkeypatch):
    monkeypatch.setenv("WATCHLIST_SOURCE", "scanner")
    _patch_source(monkeypatch, "textlist", ["nvda", " tsla"])

    source, symbols = watchlist_service.resolve_watchlist()
    assert source == "textlist"
    assert symbols == ["NVDA", "TSLA"]


def test_resolve_watchlist_finviz(monkeypatch):
    monkeypatch.setenv("WATCHLIST_SOURCE", "finviz")
    _patch_source(monkeypatch, "finviz", ["spy", "qqq", "spy"])

    source, symbols = watchlist_service.resolve_watchlist()
    assert source == "finviz"
    assert symbols == ["SPY", "QQQ"]
