from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Sequence

import streamlit as st

from ui.components.error_banner import render_error
from ui.components.kpi import render_kpi
from ui.components.line_chart import render_line_chart
from ui.services.http_client import ServiceError
from ui.state.session import get_services, get_session_state
from ui.utils.telemetry import ui_action_span
from ui.utils.time_windows import DEFAULT_WINDOWS


def _safe_fetch(label: str, func) -> Any:
    try:
        return func()
    except ServiceError as err:
        st.warning(f"{label} unavailable. See details below.")
        render_error(err)
        return []


def _extract_watchlists(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("items", "watchlists", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    return payload or []


def _watchlist_name(entry: Dict[str, Any]) -> str:
    return entry.get("name") or entry.get("bucket") or entry.get("id") or "watchlist"


def _dedupe_symbols(symbols: Sequence[str]) -> List[str]:
    return list(dict.fromkeys([s.strip().upper() for s in symbols if s]))


def _normalize_series(symbol: str, payload: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    series = []
    if isinstance(payload, dict):
        for key in ("series", "points", "bars"):
            value = payload.get(key)
            if isinstance(value, list):
                series = value
                break
    if not series and isinstance(payload, list):
        series = payload
    for entry in series:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("timestamp") or entry.get("ts")
        value = entry.get("value") or entry.get("price") or entry.get("score")
        if ts is None or value is None:
            continue
        rows.append({"timestamp": ts, "value": value, "symbol": symbol})
    return rows


def render() -> None:
    st.title("AI Trader — Overview")
    services = get_services()
    state = get_session_state()
    with ui_action_span("home.load"):
        watchlists_payload = _safe_fetch(
            "Watchlists", services.watchlists.list_watchlists
        )
        watchlists = _extract_watchlists(watchlists_payload)
        if watchlists:
            names = [_watchlist_name(wl) for wl in watchlists]
        else:
            names = ["default"]
        default_index = 0
        if state.selected_watchlist and state.selected_watchlist in names:
            default_index = names.index(state.selected_watchlist)
        selected = st.selectbox("Watchlist", options=names, index=default_index)
        state.selected_watchlist = selected

        timeframe_labels = [window.label for window in DEFAULT_WINDOWS]
        if state.timeframe not in timeframe_labels:
            state.timeframe = timeframe_labels[0]
        timeframe = st.selectbox(
            "Time window",
            options=timeframe_labels,
            index=timeframe_labels.index(state.timeframe),
        )
        state.timeframe = timeframe

        orders = _safe_fetch(
            "Orders", lambda: services.orders.list_orders({"limit": 50})
        )
        fills = _safe_fetch("Fills", lambda: services.orders.list_fills({"limit": 100}))
        jobs = _safe_fetch(
            "Sweeps", lambda: services.backtests.list_jobs({"limit": 30})
        )
        models_payload = _safe_fetch("Models", services.models.list_models)

    breadth = 0
    selected_symbols: List[str] = []
    for entry, name in zip(watchlists, names):
        if name == selected:
            symbols = entry.get("symbols") or entry.get("tickers") or []
            if isinstance(symbols, list):
                selected_symbols = _dedupe_symbols(symbols)
                breadth = len(selected_symbols)
            break

    cols = st.columns(4)
    with cols[0]:
        render_kpi("Market breadth", f"{breadth} names" if breadth else "--")
    cols[1].metric("Open orders", len(orders) if isinstance(orders, list) else "--")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_fills = 0
    if isinstance(fills, list):
        for fill in fills:
            ts = fill.get("filled_at") if isinstance(fill, dict) else None
            if ts and isinstance(ts, str):
                try:
                    ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    ts_dt = None
            else:
                ts_dt = ts
            if isinstance(ts_dt, datetime) and ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            if isinstance(ts_dt, datetime) and ts_dt >= cutoff:
                recent_fills += 1
    cols[2].metric("Fills (24h)", recent_fills if recent_fills else len(fills))
    running_jobs = (
        len(
            [
                job
                for job in jobs
                if isinstance(job, dict) and job.get("status") == "running"
            ]
        )
        if isinstance(jobs, list)
        else 0
    )
    cols[3].metric("Sweeps running", running_jobs)

    adapter_tags = []
    if isinstance(models_payload, list):
        for model in models_payload:
            if not isinstance(model, dict):
                continue
            adapter = model.get("adapter_tag") or model.get("adapter")
            name = model.get("service") or model.get("name")
            if adapter and name:
                adapter_tags.append(f"{name}:{adapter}")
    if adapter_tags:
        st.caption("Adapters: " + ", ".join(adapter_tags))

    st.subheader("Intraday signals")
    if not selected_symbols:
        st.info("Select a populated watchlist to preview symbols.")
        return

    top_symbols = selected_symbols[:3]
    intraday_cols = st.columns(len(top_symbols))
    for idx, symbol in enumerate(top_symbols):
        with intraday_cols[idx]:
            with ui_action_span("home.symbol_preview", {"symbol": symbol}):
                data = _safe_fetch(
                    f"Signals for {symbol}",
                    lambda sym=symbol: services.watchlists.signals(sym),
                )
            series = _normalize_series(symbol, data)
            if series:
                render_line_chart(symbol, series, x="timestamp", y="value")
            else:
                st.info(f"No recent data for {symbol}")
