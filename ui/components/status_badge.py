from __future__ import annotations

import streamlit as st

STATUS_COLORS = {
    "running": "#d97706",
    "completed": "#15803d",
    "failed": "#b91c1c",
    "queued": "#1d4ed8",
}


def render_status_badge(status: str) -> None:
    color = STATUS_COLORS.get(status.lower(), "#4b5563")
    st.markdown(
        f"<span style='padding:4px 8px;border-radius:8px;background:{color};color:white'>{status}</span>",
        unsafe_allow_html=True,
    )
