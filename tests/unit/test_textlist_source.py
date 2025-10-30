from __future__ import annotations

import types

import pytest

from app.sources import textlist_source
from fastapi.testclient import TestClient
from tests.conftest import _outbox, _clear_outbox, client


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.delenv("TEXTLIST_BACKENDS", raising=False)
    yield
    monkeypatch.delenv("TEXTLIST_BACKENDS", raising=False)


def test_textlist_get_symbols_dedup(monkeypatch):
    fake_module = types.SimpleNamespace(get_symbols=lambda max_symbols=None: ["NVDA", "AMD", "NVDA"])
    monkeypatch.setenv("TEXTLIST_BACKENDS", "discord")
    monkeypatch.setattr(
        textlist_source,
        "_load_backend",
        lambda name: fake_module if name == "discord" else None,
        raising=True,
    )

    symbols = textlist_source.get_symbols()
    assert symbols == ["NVDA", "AMD"]


def test_textlist_get_symbols_respects_max(monkeypatch):
    fake_module = types.SimpleNamespace(get_symbols=lambda max_symbols=None: ["NVDA", "AMD"])
    monkeypatch.setenv("TEXTLIST_BACKENDS", "discord")
    monkeypatch.setattr(textlist_source, "_load_backend", lambda name: fake_module, raising=True)

    symbols = textlist_source.get_symbols(max_symbols=1)
    assert symbols == ["NVDA"]


def test_textlist_get_symbols_no_backends(monkeypatch):
    monkeypatch.delenv("TEXTLIST_BACKENDS", raising=False)
    symbols = textlist_source.get_symbols()
    assert symbols == []
