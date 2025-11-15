from __future__ import annotations

import streamlit as st


def success(message: str) -> None:
    st.success(message)


def error(message: str) -> None:
    st.error(message)
