from __future__ import annotations

import logging
import sys
import uuid
from typing import Any, Dict

from loguru import logger

try:  # optional instrumentation
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except Exception:  # pragma: no cover - OTEL optional
    trace = None  # type: ignore
    FastAPIInstrumentor = None  # type: ignore
    Resource = None  # type: ignore
    TracerProvider = None  # type: ignore
    BatchSpanProcessor = None  # type: ignore
    OTLPSpanExporter = None  # type: ignore


class InterceptHandler(logging.Handler):
    """Redirect stdlib logging records to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - passthrough
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(exception=record.exc_info).log(level, record.getMessage())


def configure_logging(json_logs: bool = True) -> None:
    """Set up Loguru with JSON output + intercept stdlib logging."""

    logger.remove()
    logger.add(
        sys.stdout,
        serialize=json_logs,
        backtrace=False,
        diagnose=False,
    )
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)


def configure_tracing(service_name: str, resource_attrs: Dict[str, Any]) -> None:
    if not trace or not Resource or not TracerProvider:
        return
    merged = {"service.name": service_name, **resource_attrs}
    resource = Resource(attributes=merged)
    provider = TracerProvider(resource=resource)
    if BatchSpanProcessor and OTLPSpanExporter:
        processor = BatchSpanProcessor(OTLPSpanExporter())
        provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def instrument_fastapi(app) -> None:
    if FastAPIInstrumentor is None:
        return
    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        return


def request_context(request) -> dict:
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = request_id
    return {"request_id": request_id}
