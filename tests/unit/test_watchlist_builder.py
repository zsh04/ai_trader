# tests/unit/test_watchlist_builder.py
from __future__ import annotations

from typing import Dict, Iterable

from app.scanners import watchlist_builder


def _install_batch_stub(monkeypatch):
    def _fake_batch(symbols: Iterable[str]) -> Dict[str, dict]:
        return {
            sym: {"last": float(index + 1), "price_source": "stub", "ohlcv": {}}
            for index, sym in enumerate(sorted(symbols))
        }

    monkeypatch.setattr(
        watchlist_builder, "batch_latest_ohlcv", _fake_batch, raising=True
    )


def test_build_watchlist_merges_sources_case_insensitive(monkeypatch):
    _install_batch_stub(monkeypatch)
    monkeypatch.setattr(
        watchlist_builder, "scan_candidates", lambda: ["MSFT", "amd"], raising=True
    )
    monkeypatch.setattr(
        watchlist_builder,
        "finviz_fetch",
        lambda **_: ["TSLA", "msft", "goog"],
        raising=True,
    )

    result = watchlist_builder.build_watchlist(
        symbols=None,
        include_filters=False,
        include_finviz=True,
    )

    symbols = [item["symbol"] for item in result["items"]]
    assert symbols == ["AMD", "GOOG", "MSFT", "TSLA"]
    assert result["count"] == 4


def test_build_watchlist_applies_limit_after_sort(monkeypatch):
    _install_batch_stub(monkeypatch)
    monkeypatch.setattr(
        watchlist_builder, "scan_candidates", lambda: ["msft", "goog", "aapl"], raising=True
    )
    monkeypatch.setattr(
        watchlist_builder,
        "finviz_fetch",
        lambda **_: ["TSLA", "amd"],
        raising=True,
    )

    result = watchlist_builder.build_watchlist(
        include_filters=True,
        include_finviz=True,
        limit=3,
    )

    symbols = [item["symbol"] for item in result["items"]]
    assert symbols == ["AAPL", "AMD", "GOOG"]
    assert result["count"] == 3


def test_build_watchlist_manual_only_dedup(monkeypatch):
    _install_batch_stub(monkeypatch)
    monkeypatch.setattr(
        watchlist_builder, "scan_candidates", lambda: [], raising=True
    )
    monkeypatch.setattr(
        watchlist_builder, "finviz_fetch", lambda **_: [], raising=True
    )

    result = watchlist_builder.build_watchlist(
        symbols=["msft", "MSFT", "aapl"],
        include_filters=True,
    )

    symbols = [item["symbol"] for item in result["items"]]
    assert symbols == ["AAPL", "MSFT"]
    assert result["count"] == 2
