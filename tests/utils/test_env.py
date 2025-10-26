from __future__ import annotations

import importlib

import pytest


def reload_env():
    import app.utils.env as env_module

    return importlib.reload(env_module)


@pytest.fixture(autouse=True)
def _reset_env_module():
    import app.utils.env as env_module

    yield
    importlib.reload(env_module)


def test_env_defaults_when_missing(monkeypatch):
    for key in [
        "TZ",
        "TRADING_ENABLED",
        "PRICE_PROVIDERS",
        "HTTP_TIMEOUT_SECS",
    ]:
        monkeypatch.delenv(key, raising=False)

    env_module = reload_env()

    assert env_module.TZ == "America/Los_Angeles"
    assert env_module.TRADING_ENABLED is False
    assert env_module.HTTP_TIMEOUT_SECS == 10
    assert env_module.PRICE_PROVIDERS == ["alpaca", "yahoo"]


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("TRADING_ENABLED", "yes")
    monkeypatch.setenv("PRICE_PROVIDERS", "alpaca")
    monkeypatch.setenv("HTTP_TIMEOUT_SECS", "15")

    env_module = reload_env()

    assert env_module.TRADING_ENABLED is True
    assert env_module.PRICE_PROVIDERS == ["alpaca"]
    assert env_module.HTTP_TIMEOUT_SECS == 15
