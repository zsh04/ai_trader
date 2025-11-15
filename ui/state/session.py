from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import streamlit as st

from ui.settings.config import AppSettings
from ui.services.registry import ServicesRegistry
from ui.utils.request_id import generate_request_id


@dataclass
class LastAction:
    name: str
    status: str
    timestamp: float
    request_id: str


@dataclass
class SessionState:
    selected_watchlist: Optional[str] = None
    timeframe: str = "1D"
    job_filters: Dict[str, str] = field(default_factory=dict)
    active_model: Optional[str] = None
    feature_flags: Dict[str, bool] = field(default_factory=dict)
    last_request_id: str = field(default_factory=generate_request_id)
    last_actions: List[LastAction] = field(default_factory=list)

    def new_request_id(self) -> str:
        self.last_request_id = generate_request_id()
        return self.last_request_id

    def record_action(self, name: str, status: str, ts: float) -> None:
        self.last_actions.append(
            LastAction(name=name, status=status, timestamp=ts, request_id=self.last_request_id)
        )
        self.last_actions = self.last_actions[-20:]


def get_session_state() -> SessionState:
    if "_ai_trader_state" not in st.session_state:
        st.session_state["_ai_trader_state"] = SessionState()
    return st.session_state["_ai_trader_state"]


def set_settings(settings: AppSettings) -> None:
    st.session_state["_ui_settings"] = settings


def get_settings() -> AppSettings:
    return st.session_state["_ui_settings"]


def set_services(services: ServicesRegistry) -> None:
    st.session_state["_ui_services"] = services


def get_services() -> ServicesRegistry:
    return st.session_state["_ui_services"]
