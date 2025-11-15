from __future__ import annotations

import streamlit as st

from ui.services.http_client import ServiceError

ERROR_MESSAGES = {
    "user": "Check the form inputs and try again.",
    "not_found": "Resource not found. Refresh the list or adjust filters.",
    "server": "Server issue detected. Retry shortly or check API health.",
    "network": "Network error. Check connectivity or retry.",
}


def render_error(error: ServiceError) -> None:
    hint = ERROR_MESSAGES.get(error.category, "Unexpected error")
    st.error(f"{hint}\nDetails: {error}")
