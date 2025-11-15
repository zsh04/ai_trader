from __future__ import annotations

import streamlit as st


def render_drawer(title: str, content) -> None:
    with st.expander(title, expanded=False):
        if callable(content):
            content()
        else:
            st.write(content)
