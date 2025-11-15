from __future__ import annotations

import streamlit as st

from ui.state.session import get_services, get_settings
from ui.utils.telemetry import ui_action_span


def _fetch(label: str, func):
    try:
        return func()
    except Exception as err:  # ServiceError or json decode
        st.error(f"{label} check failed: {err}")
        return {}


def render() -> None:
    st.title("Health")
    services = get_services()
    settings = get_settings()
    with ui_action_span("health.live"):
        live = _fetch("live", services.health.live)
    with ui_action_span("health.ready"):
        ready = _fetch("ready", services.health.ready)
    st.metric("/health/live", live.get("status", "unknown"))
    st.metric("/health/ready", ready.get("status", "unknown"))
    st.metric("API base", settings.api_base_url)
    st.subheader("Live payload")
    st.json(live)
    st.subheader("Ready payload")
    st.json(ready)
