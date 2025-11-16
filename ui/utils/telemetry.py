from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

from ui.settings.config import AppSettings

try:  # optional dependency
    from opentelemetry import baggage, trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Status, StatusCode
except Exception:  # pragma: no cover - OTEL optional
    baggage = None  # type: ignore
    trace = None  # type: ignore
    Status = StatusCode = None  # type: ignore

logger = logging.getLogger(__name__)

_tracer = None
_telemetry_initialized = False
_faro_session_id: Optional[str] = None


def _parse_kv(raw: Optional[str]) -> Dict[str, str]:
    if not raw:
        return {}
    pairs: Dict[str, str] = {}
    for segment in raw.split(","):
        if "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        key = key.strip()
        if not key:
            continue
        pairs[key] = value.strip()
    return pairs


def init_telemetry(settings: AppSettings) -> None:
    global _tracer, _telemetry_initialized
    if _telemetry_initialized:
        return
    if trace is None or settings.otel_endpoint is None:
        logger.info("OTEL disabled for UI (missing dependency or endpoint)")
        return
    attributes = {
        "service.name": settings.service_name,
        "deployment.environment": settings.environment,
        "service.version": settings.app_version,
    }
    attributes.update(_parse_kv(settings.otel_resource_attributes))
    resource = Resource.create(attributes)
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_endpoint,
        headers=_parse_kv(settings.otel_headers),
    )
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    _tracer = provider.get_tracer(__name__)
    _telemetry_initialized = True
    logger.info("OTEL tracer initialized for UI")


def set_faro_session(session_id: Optional[str]) -> None:
    global _faro_session_id
    _faro_session_id = session_id
    if trace is None or session_id is None or baggage is None:
        return
    baggage.set_baggage("ui.session_id", session_id)


def _start_span(
    name: str, attributes: Optional[Dict[str, str]]
) -> Optional["trace.Span"]:
    if trace is None or _tracer is None:
        return None
    attrs = dict(attributes or {})
    if _faro_session_id:
        attrs.setdefault("ui.session_id", _faro_session_id)
    return _tracer.start_span(name, attributes=attrs)


@contextmanager
def _span_context(name: str, attributes: Optional[Dict[str, str]]) -> Iterator[None]:
    span = _start_span(name, attributes)
    if span is None:
        yield
        return
    try:
        with trace.use_span(span, end_on_exit=True):
            yield
    except Exception as exc:
        try:
            span.record_exception(exc)
        except TypeError:
            span.record_exception()
        if Status and StatusCode:
            span.set_status(Status(StatusCode.ERROR))
        raise


@contextmanager
def ui_action_span(
    action: str, attributes: Optional[Dict[str, str]] = None
) -> Iterator[None]:
    with _span_context(f"ui.action.{action}", attributes):
        yield


@contextmanager
def child_span(
    name: str, attributes: Optional[Dict[str, str]] = None
) -> Iterator[None]:
    with _span_context(name, attributes):
        yield
