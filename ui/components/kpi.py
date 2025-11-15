from __future__ import annotations

import streamlit as st


def render_kpi(label: str, value: str, delta: str | None = None) -> None:
    st.metric(label, value, delta)
