from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from ui.components.error_banner import render_error
from ui.components.line_chart import render_line_chart
from ui.components.table_with_toolbar import render_table
from ui.services.http_client import ServiceError
from ui.state.session import get_services
from ui.utils.telemetry import ui_action_span


def _safe_fetch(label: str, func):
    try:
        return func()
    except ServiceError as err:
        render_error(err)
        return []


def _equity_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        points = payload.get("points") or payload.get("series")
        if isinstance(points, list):
            return points
    return payload if isinstance(payload, list) else []


def render() -> None:
    st.title("Trades & Positions")
    services = get_services()
    with ui_action_span("trades.positions"):
        positions = _safe_fetch("Positions", services.trading.list_positions)
    accounts = sorted(
        {pos.get("account", "primary") for pos in positions if isinstance(pos, dict)}
    ) or ["primary"]
    account = st.selectbox("Account", options=accounts)
    with ui_action_span("trades.equity", {"account": account}):
        equity_payload = _safe_fetch(
            "Equity", lambda: services.trading.equity_curve(account)
        )
    render_line_chart(
        "Equity curve", _equity_rows(equity_payload), x="timestamp", y="equity"
    )
    render_table("Positions", positions)

    symbols = sorted(
        {
            pos.get("symbol")
            for pos in positions
            if isinstance(pos, dict) and pos.get("symbol")
        }
    )
    if symbols:
        symbol = st.selectbox(
            "Trade history symbol",
            options=[""] + symbols,
            format_func=lambda x: x or "Select…",
        )
        if symbol:
            with ui_action_span("trades.history", {"symbol": symbol}):
                trades = _safe_fetch("Trades", lambda: services.trading.trades(symbol))
            render_table(f"Trades — {symbol}", trades)
