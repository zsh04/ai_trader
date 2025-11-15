from __future__ import annotations

from typing import Iterable, Mapping

import streamlit as st


def render_table(title: str, rows: Iterable[Mapping[str, object]]) -> None:
    st.subheader(title)
    st.dataframe(list(rows))
