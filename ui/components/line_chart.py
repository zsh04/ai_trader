from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd
import streamlit as st


def render_line_chart(
    title: str, rows: Iterable[Mapping[str, object]], x: str, y: str
) -> None:
    st.subheader(title)
    df = pd.DataFrame(rows)
    if not df.empty:
        st.line_chart(df.set_index(x)[y])
    else:
        st.info("No data available")
