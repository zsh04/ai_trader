"""Centralized OpenTelemetry configuration helpers for AI Trader.

The functions in this module rely exclusively on environment variables for configuration and
gracefully degrade (no-op) when optional OpenTelemetry settings are not present.
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Type

from app.settings import get_otel_settings

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

_tracing_configured = False
_metrics_configured = False
_logging_configured = False

# Module-level handles to providers for shutdown
_tracer_provider = None
_meter_provider = None
_logger_provider = None


def configure_observability() -> bool:
    """Configure tracing, metrics, and logging exporters if the environment requests it."""
    tracing = configure_tracing()
    metrics = configure_metrics()
    logs = configure_logging()
    return tracing or metrics or logs


def configure_tracing() -> bool:
    """Configure the OpenTelemetry tracer provider if OTLP settings are present."""
    global _tracing_configured

    if _tracing_configured:
        return True
    if not _should_configure_tracing():
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning(
            "OpenTelemetry tracing dependencies not installed; tracing disabled."
        )
        return False

    try:
        resource = _build_resource(Resource)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(**_exporter_kwargs("trace")))
        )
        trace.set_tracer_provider(tracer_provider)
        global _tracer_provider
        _tracer_provider = tracer_provider
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Failed to configure tracing: %s", exc)
        return False

    _tracing_configured = True
    logger.info("Tracing configured via OpenTelemetry.")
    return True


def configure_metrics() -> bool:
    """Configure the OpenTelemetry meter provider if the environment enables metrics."""
    global _metrics_configured

    if _metrics_configured:
        return True
    if not _should_configure_metrics():
        return False

    try:
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning(
            "OpenTelemetry metrics dependencies not installed; metrics disabled."
        )
        return False

    try:
        resource = _build_resource(Resource)
        metric_exporter = OTLPMetricExporter(**_exporter_kwargs("metric"))
        reader = PeriodicExportingMetricReader(metric_exporter)
        _mp = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(_mp)
        global _meter_provider
        _meter_provider = _mp
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Failed to configure metrics: %s", exc)
        return False

    _metrics_configured = True
    logger.info("Metrics configured via OpenTelemetry.")
    return True


def configure_logging() -> bool:
    """Configure the OpenTelemetry logger provider if the environment enables log export."""
    global _logging_configured

    if _logging_configured:
        return True
    if not _should_configure_logs():
        return False

    try:
        import logging as std_logging

        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning(
            "OpenTelemetry logging dependencies not installed; log export disabled."
        )
        return False

    try:
        resource = _build_resource(Resource)
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(**_exporter_kwargs("log")))
        )
        set_logger_provider(logger_provider)
        global _logger_provider
        _logger_provider = logger_provider
        LoggingInstrumentor().instrument(set_logging_format=True)
        # Capture stdlib warnings and honor LOG_LEVEL if provided
        std_logging.captureWarnings(True)
        _level_name = os.getenv("LOG_LEVEL", "INFO").upper()
        try:
            _level = getattr(std_logging, _level_name, std_logging.INFO)
        except Exception:
            _level = std_logging.INFO
        std_logging.getLogger().setLevel(_level)
        std_logging.getLogger().debug("Python logging bridged to OpenTelemetry.")
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Failed to configure log export: %s", exc)
        return False

    _logging_configured = True
    logger.info("Log export configured via OpenTelemetry.")
    return True


def _should_configure_tracing() -> bool:
    return get_otel_settings().traces_enabled


def _should_configure_metrics() -> bool:
    return get_otel_settings().metrics_enabled


def _should_configure_logs() -> bool:
    return get_otel_settings().logs_enabled


def _exporter_kwargs(kind: str) -> Dict[str, Any]:
    settings = get_otel_settings()
    base = settings.exporter_otlp_endpoint
    if kind == "trace":
        endpoint = settings.exporter_otlp_traces_endpoint or base
    elif kind == "metric":
        endpoint = settings.exporter_otlp_metrics_endpoint or base
    else:
        endpoint = settings.exporter_otlp_logs_endpoint or base

    kwargs: Dict[str, Any] = {}
    if endpoint:
        kwargs["endpoint"] = endpoint
    headers = dict(settings.parsed_headers)
    if headers:
        kwargs["headers"] = headers
    return kwargs


def _build_resource(resource_cls: Type["Resource"]) -> "Resource":
    """Create an OpenTelemetry resource honoring OTEL_* attributes if present."""
    attributes: Dict[str, str] = {}

    settings = get_otel_settings()

    service_name = settings.service_name
    if service_name:
        attributes["service.name"] = service_name

    for key, value in settings.resource_attributes_map:
        attributes[key] = value

    default_resource = resource_cls.create({})
    if not attributes:
        return default_resource
    return default_resource.merge(resource_cls.create(attributes))


# Shutdown helper and atexit hook
def shutdown_observability() -> None:
    """Flush and shutdown OTEL providers to ensure logs/traces/metrics are exported on process exit."""
    # Shut down in reverse order of configuration
    try:
        if _logger_provider is not None:
            _logger_provider.shutdown()
    except Exception:
        logger.exception("Error during logger provider shutdown")
    try:
        if _meter_provider is not None:
            _meter_provider.shutdown()
    except Exception:
        logger.exception("Error during meter provider shutdown")
    try:
        if _tracer_provider is not None:
            _tracer_provider.shutdown()
    except Exception:
        logger.exception("Error during tracer provider shutdown")


# Ensure we always flush on app termination
atexit.register(shutdown_observability)

__all__ = [
    "configure_observability",
    "configure_tracing",
    "configure_metrics",
    "configure_logging",
    "shutdown_observability",
]
