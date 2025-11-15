from __future__ import annotations

from contextlib import contextmanager

import pytest

from ui.utils import telemetry


class DummySpan:
    def __init__(self, name: str, attributes: dict | None = None) -> None:
        self.name = name
        self.attributes = attributes or {}
        self.closed = False
        self.exceptions: list[str] = []

    def record_exception(self) -> None:
        self.exceptions.append("recorded")

    def set_status(
        self, status
    ) -> None:  # pragma: no cover - only when Status available
        self.attributes["status"] = status


class DummyTracer:
    def __init__(self) -> None:
        self.spans: list[DummySpan] = []

    def start_span(self, name: str, attributes: dict | None = None) -> DummySpan:
        span = DummySpan(name, attributes)
        self.spans.append(span)
        return span


class DummyTrace:
    def __init__(self, tracer: DummyTracer) -> None:
        self._tracer = tracer

    @contextmanager
    def use_span(self, span: DummySpan, end_on_exit: bool = True):
        yield span
        span.closed = True


class DummyBaggage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set_baggage(self, key: str, value: str) -> None:
        self.values[key] = value


def _install_dummy_tracer(monkeypatch: pytest.MonkeyPatch) -> DummyTracer:
    tracer = DummyTracer()
    monkeypatch.setattr(telemetry, "_tracer", tracer, raising=True)
    monkeypatch.setattr(telemetry, "trace", DummyTrace(tracer), raising=True)
    monkeypatch.setattr(telemetry, "baggage", DummyBaggage(), raising=True)
    telemetry.set_faro_session("faro-session-1")
    return tracer


def test_ui_action_span_records_expected_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = _install_dummy_tracer(monkeypatch)

    with telemetry.ui_action_span("home.load", {"foo": "bar"}):
        pass

    assert tracer.spans, "expected at least one span"
    span = tracer.spans[0]
    assert span.name == "ui.action.home.load"
    assert span.attributes["foo"] == "bar"
    assert span.attributes["ui.session_id"] == "faro-session-1"


def test_child_span_records_custom_name(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = _install_dummy_tracer(monkeypatch)

    with telemetry.child_span("ui.http.get", {"api.path": "/orders"}):
        pass

    span = tracer.spans[-1]
    assert span.name == "ui.http.get"
    assert span.attributes["api.path"] == "/orders"
