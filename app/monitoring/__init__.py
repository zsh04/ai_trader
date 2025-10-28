# app/monitoring/__init__.py
"""
Monitoring package

Lightweight helpers and re-exports for the monitoring/observability layer.
This file must remain dependency-free (no Streamlit/SQL imports) so that
regular app imports don't drag UI deps into server or worker processes.
"""

from __future__ import annotations

__all__ = ["running_in_streamlit", "MONITORING_VERSION"]

# Bump if we add breaking changes to the dashboard API/contract
MONITORING_VERSION = "0.1.0"


def running_in_streamlit() -> bool:
    """
    Best-effort detection if code is executing inside a Streamlit runtime.
    Safe to call from anywhere; never imports streamlit.
    """
    try:
        # Streamlit sets this env var when running a script
        import os

        if os.getenv("STREAMLIT_SERVER_ENABLED") == "1":
            return True
        # Fallback: presence of Streamlit runtime context (no import)
        # Streamlit sets this module during exec; we check by name only.
        return "streamlit" in os.sys.modules and any(
            m.startswith("streamlit.runtime") for m in os.sys.modules
        )
    except Exception:
        return False
