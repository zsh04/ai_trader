from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import streamlit as st

from ui.components.drawer import render_drawer
from ui.components.error_banner import render_error
from ui.components.status_badge import render_status_badge
from ui.components.table_with_toolbar import render_table
from ui.components.toast import error as toast_error, success as toast_success
from ui.services.http_client import ServiceError
from ui.state.session import get_services, get_session_state
from ui.utils.telemetry import ui_action_span

TERMINAL_STATES = {"completed", "failed", "cancelled"}


def _safe_jobs_fetch(limit: int) -> List[Dict[str, Any]]:
    services = get_services()
    try:
        data = services.backtests.list_jobs({"limit": limit})
    except ServiceError as err:
        render_error(err)
        return []
    return data or []


def _status_counts(jobs: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    for job in jobs:
        status = str(job.get("status", "")).lower()
        if status in counts:
            counts[status] += 1
    return counts


def _submit_sweep(form_values: Dict[str, Any]) -> None:
    services = get_services()
    state = get_session_state()
    request_id = state.new_request_id()
    payload = {
        "config_path": form_values["config_path"],
        "strategy": form_values["strategy"],
        "symbol": form_values["symbol"],
        "mode": form_values["mode"],
        "metadata": form_values["metadata"],
    }
    with ui_action_span(
        "backtests.submit",
        {"request_id": request_id, "strategy": form_values["strategy"]},
    ):
        try:
            services.backtests.submit_job(payload, request_id=request_id)
            state.record_action("backtest.submit", "queued", time.time())
            toast_success(f"Sweep enqueued ({request_id})")
        except ServiceError as err:
            state.record_action("backtest.submit", "error", time.time())
            render_error(err)
            toast_error("Failed to submit sweep")


def _poll_job(job_id: str) -> None:
    services = get_services()
    placeholder = st.empty()
    start = time.time()
    delay = 1.0
    while time.time() - start < 300:  # max 5 minutes
        try:
            details = services.backtests.job_detail(job_id)
        except ServiceError as err:
            render_error(err)
            return
        if details:
            last_status = (
                details[-1].get("status") if isinstance(details[-1], dict) else None
            )
        else:
            last_status = None
        placeholder.info(f"Polling {job_id} — status {last_status or 'unknown'}")
        if last_status and last_status.lower() in TERMINAL_STATES:
            placeholder.success(f"{job_id} reached {last_status}")
            return
        time.sleep(delay)
        delay = min(delay * 1.5, 10)
    placeholder.warning(f"Stopped polling {job_id} after 5 minutes.")


def render() -> None:
    st.title("Backtests")
    with ui_action_span("backtests.load"):
        jobs = _safe_jobs_fetch(limit=100)
    counts = _status_counts(jobs)
    cols = st.columns(4)
    cols[0].metric("Queued", counts["queued"])
    cols[1].metric("Running", counts["running"])
    cols[2].metric("Completed", counts["completed"])
    cols[3].metric("Failed", counts["failed"])

    st.subheader("Start sweep")
    with st.form("sweep_form", clear_on_submit=False):
        default_strategy = "breakout"
        strategy = st.text_input("Strategy", value=default_strategy)
        symbol = st.text_input("Symbol", value="AAPL")
        config_path = st.text_input("Config path / blob URI")
        mode = st.selectbox("Mode", options=["aca", "local"], index=0)
        metadata_raw = st.text_area("Metadata (JSON)", value="{}")
        submit = st.form_submit_button("Submit sweep")
        if submit:
            try:
                metadata = json.loads(metadata_raw or "{}")
            except json.JSONDecodeError:
                st.error("Metadata must be valid JSON.")
            else:
                _submit_sweep(
                    {
                        "strategy": strategy.strip() or default_strategy,
                        "symbol": symbol.strip() or "AAPL",
                        "config_path": config_path.strip(),
                        "mode": mode,
                        "metadata": metadata,
                    }
                )

    st.subheader("Jobs")
    render_table("Recent jobs", jobs)

    job_ids = [
        job.get("job_id") for job in jobs if isinstance(job, dict) and job.get("job_id")
    ]
    selected_job = st.selectbox(
        "Inspect job", options=[""] + job_ids, format_func=lambda x: x or "Select…"
    )
    if selected_job:
        with ui_action_span("backtests.detail", {"job_id": selected_job}):
            try:
                history = get_services().backtests.job_detail(selected_job)
            except ServiceError as err:
                render_error(err)
                history = []

        def _history_content() -> None:
            if not history:
                st.info("No events yet.")
                return
            for entry in history:
                status = (
                    entry.get("status")
                    if isinstance(entry, dict)
                    else getattr(entry, "status", "unknown")
                )
                render_status_badge(status or "unknown")
                st.json(entry)

        render_drawer(f"Job {selected_job} history", _history_content)
        poll = st.button("Poll selected job", key=f"poll-{selected_job}")
        if poll:
            with ui_action_span("backtests.poll", {"job_id": selected_job}):
                _poll_job(selected_job)
