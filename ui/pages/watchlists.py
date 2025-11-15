from __future__ import annotations

import time
from typing import Any, Dict, List

import streamlit as st

from ui.components.error_banner import render_error
from ui.components.table_with_toolbar import render_table
from ui.components.toast import error as toast_error
from ui.components.toast import success as toast_success
from ui.services.http_client import ServiceError
from ui.state.session import get_services, get_session_state
from ui.utils.telemetry import ui_action_span


def _safe_list() -> List[Dict[str, Any]]:
    services = get_services()
    try:
        data = services.watchlists.list_watchlists()
    except ServiceError as err:
        render_error(err)
        return []
    if isinstance(data, dict):
        return data.get("items") or data.get("watchlists") or []
    return data or []


def _parse_symbols(raw: str) -> List[str]:
    tokens = [token.strip().upper() for token in raw.replace("\n", ",").split(",")]
    return list(dict.fromkeys([token for token in tokens if token]))


def _save_watchlist(bucket: str, symbols: List[str], tags: List[str]) -> None:
    services = get_services()
    state = get_session_state()
    request_id = state.new_request_id()
    payload = {
        "bucket": bucket,
        "symbols": symbols,
        "tags": tags,
        "source": "streamlit-ui",
    }
    with ui_action_span(
        "watchlists.save", {"bucket": bucket, "request_id": request_id}
    ):
        try:
            services.watchlists.save_watchlist(payload, request_id=request_id)
            state.record_action(f"watchlist:{bucket}", "saved", time.time())
            toast_success(f"Saved {bucket} ({len(symbols)} symbols)")
            st.experimental_rerun()
        except ServiceError as err:
            render_error(err)
            toast_error("Failed to save watchlist")


def render() -> None:
    st.title("Watchlists")
    with ui_action_span("watchlists.load"):
        watchlists = _safe_list()
    names = [
        wl.get("name") or wl.get("bucket") for wl in watchlists if isinstance(wl, dict)
    ]
    selected_idx = 0 if names else -1
    selected_bucket = (
        st.selectbox("Existing lists", options=names, index=selected_idx)
        if names
        else None
    )
    preview_symbols: List[str] = []
    if selected_bucket:
        selected = next(
            (
                wl
                for wl in watchlists
                if (wl.get("name") or wl.get("bucket")) == selected_bucket
            ),
            {},
        )
        preview_symbols = selected.get("symbols") or selected.get("tickers") or []
        st.caption(
            f"{selected_bucket} · {len(preview_symbols)} symbols · Source {selected.get('source', 'n/a')}"
        )
        render_table(
            "Latest watchlist snapshot", [{"symbol": sym} for sym in preview_symbols]
        )

    st.subheader("Builder")
    bucket = st.text_input("Name", value=selected_bucket or "new-list").strip().lower()
    tags_raw = st.text_input("Tags (comma separated)")
    tags = [tag.strip().lower() for tag in tags_raw.split(",") if tag.strip()]
    symbols_raw = st.text_area("Symbols", value=", ".join(preview_symbols[:10]))
    symbols = _parse_symbols(symbols_raw)
    st.caption(f"{len(symbols)} unique symbols after dedupe")
    if st.button("Save watchlist", type="primary", disabled=not bucket or not symbols):
        _save_watchlist(bucket, symbols, tags)

    st.subheader("Signal preview")
    preview_target = st.selectbox(
        "Preview symbol", options=[""] + symbols, format_func=lambda x: x or "Select…"
    )
    if preview_target:
        services = get_services()
        with ui_action_span("watchlists.signals", {"symbol": preview_target}):
            try:
                preview = services.watchlists.signals(preview_target)
            except ServiceError as err:
                render_error(err)
                preview = []
        rows = preview if isinstance(preview, list) else ([preview] if preview else [])
        render_table(f"Signals — {preview_target}", rows)
