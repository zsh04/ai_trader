from __future__ import annotations

import importlib
import os

import pytest


def _reload_config(monkeypatch, env: dict[str, str] | None = None):
    env = env or {}
    for key in [
        "PORT",
        "TZ",
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
        "ALPACA_BASE_URL",
        "PAPER_TRADING",
        "AZURE_STORAGE_ACCOUNT_NAME",
        "AZURE_STORAGE_ACCOUNT_KEY",
        "AZURE_STORAGE_CONTAINER_NAME",
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "PGSSLMODE",
        "PRICE_MIN",
        "PRICE_MAX",
        "GAP_MIN_PCT",
        "RVOL_MIN",
        "SPREAD_MAX_PCT_PRE",
        "DOLLAR_VOL_MIN_PRE",
        "MAX_WATCHLIST",
    ]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import app.utils.env as env_module

    importlib.reload(env_module)
    import app.config as config_module

    importlib.reload(config_module)
    return config_module


def test_settings_defaults_are_deterministic(monkeypatch):
    config_module = _reload_config(monkeypatch)
    settings = config_module.settings

    assert settings.port == 8000
    assert settings.tz == "America/Los_Angeles"
    assert settings.blob_container == "traderdata"
    assert settings.max_watchlist == 15


def test_settings_respect_env_overrides(monkeypatch):
    config_module = _reload_config(
        monkeypatch,
        env={
            "PORT": "9000",
            "TZ": "UTC",
            "ALPACA_API_KEY": "abc",
            "AZURE_STORAGE_ACCOUNT_NAME": "acct",
            "AZURE_STORAGE_ACCOUNT_KEY": "key",
            "AZURE_STORAGE_CONTAINER_NAME": "bucket",
            "MAX_WATCHLIST": "25",
        },
    )

    settings = config_module.settings
    from app import __version__

    assert settings.VERSION == __version__
    assert settings.port == 9000
    assert settings.tz == "UTC"
    assert settings.alpaca_key == "abc"
    assert settings.blob_account == "acct"
    assert settings.blob_key == "key"
    assert settings.blob_container == "bucket"
    assert settings.max_watchlist == 25
