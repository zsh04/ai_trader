"""Minimal helpers for optional backtest telemetry."""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Dict

try:  # Optional dependency
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
            name="backtest_runs_total",
            unit="1",
            description="Number of backtest runs completed",
        )
        if _meter
        else None
    )
except Exception:  # pragma: no cover - guard against SDK mismatches
    _run_counter = None


def start_span(attributes: Dict[str, Any]):
    if not _tracer:
        return nullcontext()
    try:
        return _tracer.start_as_current_span("backtest.run", attributes=attributes)
    except Exception:  # pragma: no cover
        return nullcontext()


def record_run(attributes: Dict[str, Any]) -> None:
    if not _run_counter:
        return
    try:
        _run_counter.add(1, attributes=attributes)
    except Exception:  # pragma: no cover
        return


__all__ = ["start_span", "record_run"]
