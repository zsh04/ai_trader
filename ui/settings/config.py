from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


class SettingsError(RuntimeError):
    """Raised when required UI settings are missing or invalid."""


@dataclass(frozen=True)
class AppSettings:
    api_base_url: str
    service_name: str
    environment: str
    app_version: str
    otel_endpoint: Optional[str]
    otel_protocol: Optional[str]
    otel_resource_attributes: Optional[str]
    otel_headers: Optional[str]
    faro_url: Optional[str]
    faro_app_id: Optional[str]
    feature_chronos2: bool
    feature_backtest_sweeps: bool
    feature_demo_data: bool


REQUIRED_ENV_VARS = ["API_BASE_URL"]


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> AppSettings:
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise SettingsError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return AppSettings(
        api_base_url=os.environ["API_BASE_URL"].rstrip("/"),
        service_name=os.getenv("SERVICE_NAME", "ai-trader-ui"),
        environment=os.getenv("ENV", "dev"),
        app_version=os.getenv("APP_VERSION", "0.0.0"),
        otel_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
        otel_protocol=os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL"),
        otel_resource_attributes=os.getenv("OTEL_RESOURCE_ATTRIBUTES"),
        otel_headers=os.getenv("OTEL_EXPORTER_OTLP_HEADERS"),
        faro_url=os.getenv("FARO_URL"),
        faro_app_id=os.getenv("FARO_APP_ID"),
        feature_chronos2=_get_bool("FEATURE_CHRONOS2"),
        feature_backtest_sweeps=_get_bool("FEATURE_BACKTEST_SWEEPS", default=True),
        feature_demo_data=_get_bool("FEATURE_DEMO_DATA"),
    )
