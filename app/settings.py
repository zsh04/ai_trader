"""Centralized application settings powered by Pydantic.

Environment matrix:

| Section  | Environment Variable            | Default                     | Purpose                                  |
|----------|---------------------------------|-----------------------------|------------------------------------------|
| OTEL     | `OTEL_EXPORTER_OTLP_ENDPOINT`   | `None`                      | Root OTLP collector endpoint             |
| OTEL     | `OTEL_EXPORTER_OTLP_HEADERS`    | `None`                      | Additional OTLP request headers          |
| OTEL     | `OTEL_SERVICE_NAME`             | `ai-trader`                 | Logical service identifier               |
| OTEL     | `OTEL_RESOURCE_ATTRIBUTES`      | `None`                      | Extra resource attributes (key=value)    |
| OTEL     | `OTEL_LOGS_EXPORTER`            | `None`                      | Logs exporter implementation             |
| OTEL     | `OTEL_TRACES_EXPORTER`          | `None`                      | Traces exporter implementation           |
| OTEL     | `OTEL_METRICS_EXPORTER`         | `None`                      | Metrics exporter implementation          |
| Sentry   | `SENTRY_DSN`                    | `None`                      | Sentry ingest DSN                        |
| Sentry   | `SENTRY_TRACES_SAMPLE_RATE`     | `0.0`                       | Fraction of transactions to trace        |
| Sentry   | `SENTRY_ENVIRONMENT`            | `None`                      | Deployment environment label             |
| Database | `DATABASE_URL`                  | `None`                      | Primary Postgres connection URI          |
| Database | `TEST_DATABASE_URL`             | `None`                      | Fallback Postgres URI for tests/CI       |
| Database | `PGHOST`                        | `localhost`                 | Postgres host when building DSN manually |
| Database | `PGPORT`                        | `5432`                      | Postgres port                            |
| Database | `PGDATABASE`                    | `ai_trader`                 | Postgres database                        |
| Database | `PGUSER`                        | `postgres`                  | Postgres user                            |
| Database | `PGPASSWORD`                    | `""`                        | Postgres password                        |
| Database | `PGSSLMODE`                     | `prefer`                    | Postgres SSL mode                        |

The settings objects below expose structured access to these values along with a few
helper properties to streamline conditional logic (e.g., whether tracing or Sentry is
enabled). They source environment variables at import-time and are intended to be
treated as read-only.
"""

from __future__ import annotations

from functools import cached_property
from typing import List, Tuple
from urllib.parse import quote_plus

from pydantic import BaseModel, Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class _SettingsBase(BaseSettings):
    """Common configuration for BaseSettings subclasses."""

    model_config = SettingsConfigDict(
        env_prefix="",
        populate_by_name=True,
        extra="ignore",
        case_sensitive=True,
        frozen=True,
    )


class OTELSettings(_SettingsBase):
    """OpenTelemetry exporter configuration."""

    exporter_otlp_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    exporter_otlp_traces_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
    )
    exporter_otlp_metrics_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"
    )
    exporter_otlp_logs_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"
    )
    exporter_otlp_headers: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_HEADERS"
    )
    logs_exporter: str | None = Field(default=None, alias="OTEL_LOGS_EXPORTER")
    traces_exporter: str | None = Field(default=None, alias="OTEL_TRACES_EXPORTER")
    metrics_exporter: str | None = Field(default=None, alias="OTEL_METRICS_EXPORTER")
    service_name: str = Field(default="ai-trader", alias="OTEL_SERVICE_NAME")
    resource_attributes: str | None = Field(
        default=None, alias="OTEL_RESOURCE_ATTRIBUTES"
    )
    python_log_level: str | None = Field(default=None, alias="OTEL_PYTHON_LOG_LEVEL")

    @computed_field
    @property
    def traces_enabled(self) -> bool:
        return any(
            value
            for value in (
                self.exporter_otlp_endpoint,
                self.exporter_otlp_traces_endpoint,
                self.traces_exporter,
            )
        )

    @computed_field
    @property
    def metrics_enabled(self) -> bool:
        return any(
            value
            for value in (
                self.exporter_otlp_endpoint,
                self.exporter_otlp_metrics_endpoint,
                self.metrics_exporter,
            )
        )

    @computed_field
    @property
    def logs_enabled(self) -> bool:
        return any(
            value
            for value in (
                self.exporter_otlp_endpoint,
                self.exporter_otlp_logs_endpoint,
                self.logs_exporter,
            )
        )

    @computed_field
    @property
    def parsed_headers(self) -> Tuple[Tuple[str, str], ...]:
        raw = (self.exporter_otlp_headers or "").strip()
        if not raw:
            return tuple()
        pairs: List[Tuple[str, str]] = []
        for part in raw.split(","):
            key, _, value = part.partition("=")
            key = key.strip()
            value = value.strip()
            if key and value:
                pairs.append((key, value))
        return tuple(pairs)

    @computed_field
    @property
    def resource_attributes_map(self) -> Tuple[Tuple[str, str], ...]:
        raw = (self.resource_attributes or "").strip()
        if not raw:
            return tuple()
        pairs: List[Tuple[str, str]] = []
        for part in raw.split(","):
            key, _, value = part.partition("=")
            key = key.strip()
            value = value.strip()
            if key and value:
                pairs.append((key, value))
        return tuple(pairs)


class SentrySettings(_SettingsBase):
    """Sentry SDK configuration."""

    dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    traces_sample_rate: float = Field(default=0.0, alias="SENTRY_TRACES_SAMPLE_RATE")
    environment: str | None = Field(default=None, alias="SENTRY_ENVIRONMENT")

    @computed_field
    @property
    def enabled(self) -> bool:
        return bool(self.dsn)


class DatabaseSettings(_SettingsBase):
    """Postgres configuration, supports DSN override or manual assembly."""

    url: str | None = Field(default=None, alias="DATABASE_URL")
    test_url: str | None = Field(default=None, alias="TEST_DATABASE_URL")
    host: str = Field(default="localhost", alias="PGHOST")
    port: int = Field(default=5432, alias="PGPORT")
    name: str = Field(default="ai_trader", alias="PGDATABASE")
    user: str = Field(default="postgres", alias="PGUSER")
    password: str = Field(default="", alias="PGPASSWORD")
    sslmode: str = Field(default="prefer", alias="PGSSLMODE")

    @field_validator("port", mode="before")
    @classmethod
    def _coerce_port(cls, value: int | str | None) -> int:
        if value in (None, ""):
            return 5432
        try:
            return int(value)
        except (TypeError, ValueError):
            return 5432

    @computed_field
    @property
    def primary_dsn(self) -> str | None:
        return self.url or self.test_url

    @cached_property
    def assembled_dsn(self) -> str:
        user = quote_plus(self.user or "")
        password = quote_plus(self.password or "")
        return (
            f"postgresql+psycopg2://{user}:{password}@"
            f"{self.host}:{self.port}/{self.name}?sslmode={self.sslmode}"
        )

    def effective_dsn(self) -> str | None:
        return self.primary_dsn or self.assembled_dsn


class MarketDataSettings(_SettingsBase):
    """API credentials and feature flags for external market data vendors."""

    alphavantage_key: str | None = Field(default=None, alias="ALPHAVANTAGE_API_KEY")
    finnhub_key: str | None = Field(default=None, alias="FINNHUB_API_KEY")

    @computed_field
    @property
    def has_alphavantage(self) -> bool:
        return bool(self.alphavantage_key)

    @computed_field
    @property
    def has_finnhub(self) -> bool:
        return bool(self.finnhub_key)


class Settings(BaseModel):
    """Aggregate accessor for domain-specific settings."""

    otel: OTELSettings = Field(default_factory=OTELSettings)
    sentry: SentrySettings = Field(default_factory=SentrySettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    market_data: MarketDataSettings = Field(default_factory=MarketDataSettings)

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }


def get_settings() -> Settings:
    """Instantiate settings from the current environment."""
    return Settings()


def reload_settings() -> Settings:
    """Alias for get_settings to maintain a consistent API."""
    return get_settings()


def get_otel_settings() -> OTELSettings:
    return get_settings().otel


def get_sentry_settings() -> SentrySettings:
    return get_settings().sentry


def get_database_settings() -> DatabaseSettings:
    return get_settings().database


def get_market_data_settings() -> MarketDataSettings:
    return get_settings().market_data


__all__ = [
    "Settings",
    "get_settings",
    "reload_settings",
    "get_otel_settings",
    "get_sentry_settings",
    "get_database_settings",
    "OTELSettings",
    "SentrySettings",
    "DatabaseSettings",
    "MarketDataSettings",
    "get_market_data_settings",
]
