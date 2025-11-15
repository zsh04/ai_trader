from __future__ import annotations

import uuid

import streamlit as st

from ui.settings.config import AppSettings
from ui.utils.telemetry import set_faro_session


def bootstrap_rum(settings: AppSettings) -> None:
    """
    Injects the Faro RUM snippet (when configured) and propagates the session ID
    into OTEL baggage for trace correlation.
    """
    if not settings.faro_url or not settings.faro_app_id:
        return
    if st.session_state.get("_faro_bootstrapped"):
        return
    session_id = st.session_state.get("_faro_session_id") or uuid.uuid4().hex
    st.session_state["_faro_session_id"] = session_id
    script = f"""
    <script>
      window.__AI_TRADER_FARO__ = {{
        appId: "{settings.faro_app_id}",
        sessionId: "{session_id}",
        environment: "{settings.environment}",
        version: "{settings.app_version}"
      }};
    </script>
    <script defer src="{settings.faro_url}"></script>
    """
    st.markdown(script, unsafe_allow_html=True)
    st.session_state["_faro_bootstrapped"] = True
    set_faro_session(session_id)
