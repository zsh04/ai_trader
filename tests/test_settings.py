from __future__ import annotations

from app import settings as settings_module


def test_otel_settings_flags(monkeypatch):
    for key in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_TRACES_EXPORTER",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_METRICS_EXPORTER",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "OTEL_LOGS_EXPORTER",
    ):
        monkeypatch.delenv(key, raising=False)

    settings_module.reload_settings()
    otel = settings_module.get_otel_settings()
    assert otel.traces_enabled is False
    assert otel.metrics_enabled is False
    assert otel.logs_enabled is False

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.namespace=ai,env=local")
    settings_module.reload_settings()
    otel = settings_module.get_otel_settings()

    assert otel.traces_enabled is True
    assert otel.metrics_enabled is True
    assert otel.logs_enabled is True
    assert ("service.namespace", "ai") in otel.resource_attributes_map
    assert ("env", "local") in otel.resource_attributes_map


def test_telegram_settings_parses_allowlist(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123 , 456,notint, 789 ")
    monkeypatch.setenv("TELEGRAM_TIMEOUT_SECS", "15")
    monkeypatch.setenv("TELEGRAM_FAKE", "1")

    settings_module.reload_settings()
    telegram = settings_module.get_telegram_settings()
    assert telegram.allowed_user_ids == (123, 456, 789)
    assert telegram.timeout_secs == 15
    assert telegram.fake_mode is True


def test_database_settings_fallback(monkeypatch):
    for key in ("DATABASE_URL", "TEST_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PGUSER", "user")
    monkeypatch.setenv("PGPASSWORD", "p@ss word")
    monkeypatch.setenv("PGHOST", "db.local")
    monkeypatch.setenv("PGPORT", "6543")
    monkeypatch.setenv("PGDATABASE", "trader")
    monkeypatch.setenv("PGSSLMODE", "require")

    settings_module.reload_settings()
    db = settings_module.get_database_settings()
    assert db.primary_dsn is None
    assembled = db.assembled_dsn
    assert "user" in assembled
    assert "p%40ss+word" in assembled
    assert "db.local:6543" in assembled
    assert db.effective_dsn() == assembled


def test_reload_settings_returns_fresh_instance(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@sentry.example/1")
    s1 = settings_module.get_settings()
    s2 = settings_module.reload_settings()
    assert s1.sentry.dsn == "https://public@sentry.example/1"
    assert s2.sentry.dsn == "https://public@sentry.example/1"
    assert s1 is not s2


def test_market_data_settings(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "alpha-key")
    monkeypatch.setenv("FINNHUB_API_KEY", "finn-key")
    settings_module.reload_settings()
    market = settings_module.get_market_data_settings()
    assert market.alphavantage_key == "alpha-key"
    assert market.finnhub_key == "finn-key"
    assert market.has_alphavantage is True
    assert market.has_finnhub is True
