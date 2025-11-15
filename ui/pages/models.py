from __future__ import annotations

import time
from typing import Any, Dict

import streamlit as st

from ui.components.error_banner import render_error
from ui.components.status_badge import render_status_badge
from ui.components.toast import error as toast_error
from ui.components.toast import success as toast_success
from ui.services.http_client import ServiceError
from ui.state.session import get_services, get_session_state
from ui.utils.telemetry import ui_action_span


def _safe_models_fetch():
    services = get_services()
    try:
        return services.models.list_models()
    except ServiceError as err:
        render_error(err)
        return []


def _model_status(entry: Dict[str, Any]) -> str:
    for key in ("status", "state", "health"):
        if key in entry and isinstance(entry[key], str):
            return entry[key]
    return "unknown"


def _adapter_tag(entry: Dict[str, Any]) -> str:
    return entry.get("adapter_tag") or entry.get("adapter") or "n/a"


def _handle_model_action(action: str, service_name: str):
    services = get_services()
    state = get_session_state()
    request_id = state.new_request_id()
    handler = {
        "warm": services.models.warm,
        "sync": services.models.sync_adapter,
        "shadow": services.models.toggle_shadow,
    }[action]
    with ui_action_span(
        f"models.{action}", {"service": service_name, "request_id": request_id}
    ):
        try:
            handler(service_name, request_id=request_id)
            state.record_action(f"{action}:{service_name}", "ok", time.time())
            toast_success(f"{action.title()} sent to {service_name} ({request_id})")
        except ServiceError as err:
            state.record_action(f"{action}:{service_name}", "error", time.time())
            render_error(err)
            toast_error(f"Failed to {action} {service_name}")


def render() -> None:
    st.title("Models")
    with ui_action_span("models.load"):
        models_payload = _safe_models_fetch()
    if not models_payload:
        st.info("No models reported by the control plane.")
        return
    for entry in models_payload:
        if not isinstance(entry, dict):
            continue
        service_name = entry.get("service") or entry.get("name") or "model"
        adapter = _adapter_tag(entry)
        warm = entry.get("warm") or entry.get("warmed")
        readiness = "warm" if warm else "cold"
        with st.container(border=True):
            st.subheader(service_name.title())
            render_status_badge(_model_status(entry))
            st.caption(f"Adapter: {adapter} · Cached: {readiness}")
            cols = st.columns(3)
            if cols[0].button(f"Warm {service_name}", key=f"warm-{service_name}"):
                _handle_model_action("warm", service_name)
            if cols[1].button(
                f"Sync adapter {service_name}", key=f"sync-{service_name}"
            ):
                _handle_model_action("sync", service_name)
            if cols[2].button(
                f"Toggle shadow {service_name}", key=f"shadow-{service_name}"
            ):
                _handle_model_action("shadow", service_name)
