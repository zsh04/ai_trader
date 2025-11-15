from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

import streamlit as st

from ui.components.error_banner import render_error
from ui.components.table_with_toolbar import render_table
from ui.services.http_client import ServiceError
from ui.state.session import get_services
from ui.utils.telemetry import ui_action_span


def _load_with_latency(label: str, loader) -> Tuple[List[Dict[str, Any]], float]:
    start = time.perf_counter()
    try:
        data = loader() or []
    except ServiceError as err:
        render_error(err)
        data = []
    latency = time.perf_counter() - start
    if not data and latency > 2.0:
        st.warning(
            f"{label} API empty after {latency:.1f}s. Retry or check backend availability.",
            icon="⚠️",
        )
    return data, latency


def render() -> None:
    st.title("Orders & Fills")
    services = get_services()
    tab_orders, tab_fills = st.tabs(["Orders", "Fills"])
    selected_order = ""

    with tab_orders:
        symbol = st.text_input("Symbol filter", key="orders_symbol").strip().upper()
        with ui_action_span("orders.list", {"symbol": symbol or "all"}):
            params = {"limit": 50}
            if symbol:
                params["symbol"] = symbol
            orders, order_latency = _load_with_latency(
                "Orders", lambda: services.orders.list_orders(params)
            )
        render_table("Orders", orders)
        order_ids = [order.get("id") for order in orders if isinstance(order, dict)]
        selected_order = st.selectbox(
            "Link fills to order",
            options=[""] + order_ids,
            format_func=lambda x: x or "None",
        )

    with tab_fills:
        symbol_filter = (
            st.text_input("Symbol filter", key="fills_symbol").strip().upper()
        )
        with ui_action_span("fills.list", {"symbol": symbol_filter or "all"}):
            params = {"limit": 100}
            if symbol_filter:
                params["symbol"] = symbol_filter
            fills, fill_latency = _load_with_latency(
                "Fills", lambda: services.orders.list_fills(params)
            )
        if selected_order:
            linked = [fill for fill in fills if fill.get("order_id") == selected_order]
            if linked:
                st.info(f"Showing fills for order {selected_order}")
                render_table("Linked fills", linked)
            else:
                st.warning("No fills yet for selected order.")
        render_table("Fills (latest)", fills)
