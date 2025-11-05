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
        "HTTP_TIMEOUT",
        "HTTP_RETRIES",
        "HTTP_BACKOFF",
    ]:
        monkeypatch.delenv(key, raising=False)

    env_module = reload_env()

    assert env_module.TZ == "America/Los_Angeles"
    assert env_module.TRADING_ENABLED is False
    assert env_module.HTTP_TIMEOUT_SECS == 10
    assert env_module.HTTP_TIMEOUT == 10
    assert env_module.HTTP_RETRIES == 2
    assert env_module.HTTP_BACKOFF == 1.5
    assert env_module.PRICE_PROVIDERS == ["alpaca", "yahoo"]


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("TRADING_ENABLED", "yes")
    monkeypatch.setenv("PRICE_PROVIDERS", "alpaca")
    monkeypatch.setenv("HTTP_TIMEOUT", "15")
    monkeypatch.setenv("HTTP_RETRIES", "5")
    monkeypatch.setenv("HTTP_BACKOFF", "2.0")
    monkeypatch.setenv("HTTP_TIMEOUT_SECS", "99")

    env_module = reload_env()

    assert env_module.TRADING_ENABLED is True
    assert env_module.PRICE_PROVIDERS == ["alpaca"]
    assert env_module.HTTP_TIMEOUT_SECS == 15
    assert env_module.HTTP_TIMEOUT == 15
    assert env_module.HTTP_RETRIES == 5
    assert env_module.HTTP_BACKOFF == 2.0


def test_env_legacy_http_settings(monkeypatch):
    monkeypatch.delenv("HTTP_TIMEOUT", raising=False)
    monkeypatch.delenv("HTTP_RETRIES", raising=False)
    monkeypatch.delenv("HTTP_BACKOFF", raising=False)
    monkeypatch.setenv("HTTP_TIMEOUT_SECS", "25")
    monkeypatch.setenv("HTTP_RETRY_ATTEMPTS", "4")
    monkeypatch.setenv("HTTP_RETRY_BACKOFF_SEC", "3.5")

    env_module = reload_env()

    assert env_module.HTTP_TIMEOUT == 25
    assert env_module.HTTP_RETRIES == 4
    assert env_module.HTTP_BACKOFF == 3.5
