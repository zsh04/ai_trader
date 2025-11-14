"""Telemetry helpers for LangGraph router."""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Dict

try:  # optional dependency
    from opentelemetry import trace
except Exception:  # pragma: no cover - OTEL optional
    trace = None  # type: ignore

try:
    from opentelemetry.metrics import get_meter
except Exception:  # pragma: no cover
    get_meter = None  # type: ignore


_tracer = trace.get_tracer(__name__) if trace else None
_meter = get_meter(__name__) if get_meter else None

try:
    _run_counter = (
        _meter.create_counter(
            name="router_runs_total",
            unit="1",
            description="Number of LangGraph router runs",
        )
        if _meter
        else None
    )
except Exception:  # pragma: no cover - guard against SDK mismatches
    _run_counter = None


def start_router_span(attributes: Dict[str, Any]):
    if not _tracer:
        return nullcontext()
    try:
        return _tracer.start_as_current_span("router.run", attributes=attributes)
    except Exception:  # pragma: no cover
        return nullcontext()


def start_node_span(name: str, attributes: Dict[str, Any] | None = None):
    if not _tracer:
        return nullcontext()
    attrs = {"router.node": name}
    if attributes:
        attrs.update(attributes)
    try:
        return _tracer.start_as_current_span(f"router.node.{name}", attributes=attrs)
    except Exception:  # pragma: no cover
        return nullcontext()


def record_run(attributes: Dict[str, Any]) -> None:
    if not _run_counter:
        return
    try:
        _run_counter.add(1, attributes=attributes)
    except Exception:  # pragma: no cover
        return


__all__ = ["start_router_span", "start_node_span", "record_run"]
