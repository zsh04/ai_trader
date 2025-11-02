"""
Telemetry adapters (logging, metrics, tracing).

Provides:
- setup_logging()
- logger
- setup_tracing(service_name: str)
"""

import os
import sys

from loguru import logger

from .loguru import PropagateHandler


# --- Logging setup ---


def setup_logging() -> None:
    """Initialize application-wide logging with level from LOG_LEVEL env var and detailed format including module and line number."""
    level = os.getenv("LOG_LEVEL", "INFO")
    logger.remove()
    logger.add(sys.stdout, colorize=True, level=level.upper())
    logger.add(PropagateHandler(), format="{message}")


# --- Tracing (future integration placeholder) ---


def setup_tracing(service_name: str) -> None:
    """
    Stub for OpenTelemetry tracing integration.
    Future: configure OTLP exporter to Azure Monitor or Grafana Cloud.
    """
    os.environ.setdefault("AI_TRADER_OTEL_SERVICE_NAME", service_name)
    logger.info(f"Tracing initialized for {service_name}")
    # To extend: integrate OpenTelemetry SDK here, e.g.,
    # from opentelemetry import trace
    # from opentelemetry.sdk.trace import TracerProvider
    # from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    # trace.set_tracer_provider(TracerProvider())
    # tracer = trace.get_tracer(__name__)
    # span_processor = BatchSpanProcessor(ConsoleSpanExporter())
    # trace.get_tracer_provider().add_span_processor(span_processor)


__all__ = ["setup_logging", "logger", "setup_tracing"]
