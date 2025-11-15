from __future__ import annotations

import logging

import streamlit as st

from ui.pages import (
    backtests,
    health,
    home,
    models,
    orders_fills,
    trades_positions,
    watchlists,
)
from ui.pages.settings_page import render as render_settings
from ui.services.registry import build_services
from ui.settings.config import SettingsError, load_settings
from ui.state.session import (
    get_session_state,
    set_services,
    set_settings,
)
from ui.utils.rum import bootstrap_rum
from ui.utils.telemetry import init_telemetry

logger = logging.getLogger(__name__)

PAGE_MAP = {
    "Home": home.render,
    "Models": models.render,
    "Backtests": backtests.render,
    "Orders & Fills": orders_fills.render,
    "Trades & Positions": trades_positions.render,
    "Watchlists": watchlists.render,
    "Health": health.render,
}


def main() -> None:
    st.set_page_config(page_title="AI Trader Console", layout="wide")
    try:
        settings = load_settings()
    except SettingsError as exc:
        st.error(f"Configuration error: {exc}\nSet API_BASE_URL to continue.")
        logger.error("UI failed fast: %s", exc)
        return

    set_settings(settings)
    if "_ui_services" not in st.session_state:
        set_services(build_services(settings))

    init_telemetry(settings)
    bootstrap_rum(settings)
    _ = get_session_state()
    st.sidebar.title("Navigation")
    st.sidebar.caption(
        f"API base: {settings.api_base_url}\n\nEnv: {settings.environment}\nVersion: {settings.app_version}"
    )
    page_name = st.sidebar.radio(
        "Go to", list(PAGE_MAP.keys()) + ["Settings"], key="nav"
    )
    if page_name == "Settings":
        render_settings(settings)
        return

    PAGE_MAP[page_name]()


if __name__ == "__main__":
    main()
