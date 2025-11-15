from __future__ import annotations

import streamlit as st

from ui.settings.config import AppSettings


def render(settings: AppSettings) -> None:
    st.title("Settings")
    col1, col2 = st.columns(2)
    col1.metric("Environment", settings.environment)
    col1.metric("Service name", settings.service_name)
    col2.metric("API base", settings.api_base_url)
    col2.metric("Version", settings.app_version)

    st.subheader("Feature flags")
    st.json(
        {
            "FEATURE_CHRONOS2": settings.feature_chronos2,
            "FEATURE_BACKTEST_SWEEPS": settings.feature_backtest_sweeps,
            "FEATURE_DEMO_DATA": settings.feature_demo_data,
        }
    )
    st.subheader("Telemetry")
    st.json(
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT": settings.otel_endpoint,
            "OTEL_EXPORTER_OTLP_PROTOCOL": settings.otel_protocol,
            "OTEL_RESOURCE_ATTRIBUTES": settings.otel_resource_attributes,
            "OTEL_EXPORTER_OTLP_HEADERS": settings.otel_headers,
            "FARO_URL": settings.faro_url,
            "FARO_APP_ID": settings.faro_app_id,
        }
    )
