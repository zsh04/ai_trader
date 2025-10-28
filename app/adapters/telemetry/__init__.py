"""
Telemetry adapters (logging, metrics, tracing).

Provides:
- setup_logging()
- get_logger(name: str)
- setup_tracing(service_name: str)
"""

import logging
import os
from typing import Optional

# --- Logging setup ---


def setup_logging() -> None:
    """Initialize application-wide logging with level from LOG_LEVEL env var and detailed format including module and line number."""
    level = os.getenv("LOG_LEVEL", "INFO")
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(lineno)d | %(message)s"
    )
    logging.basicConfig(level=log_level, format=log_fmt, force=True)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger with standardized formatting and global config applied."""
    return logging.getLogger(name or "ai_trader")


# --- Tracing (future integration placeholder) ---


def setup_tracing(service_name: str) -> None:
    """
    Stub for OpenTelemetry tracing integration.
    Future: configure OTLP exporter to Azure Monitor or Grafana Cloud.
    """
    os.environ.setdefault("AI_TRADER_OTEL_SERVICE_NAME", service_name)
    logging.getLogger("ai_trader.telemetry").info(
        f"Tracing initialized for {service_name}"
    )
    # To extend: integrate OpenTelemetry SDK here, e.g.,
    # from opentelemetry import trace
    # from opentelemetry.sdk.trace import TracerProvider
    # from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    # trace.set_tracer_provider(TracerProvider())
    # tracer = trace.get_tracer(__name__)
    # span_processor = BatchSpanProcessor(ConsoleSpanExporter())
    # trace.get_tracer_provider().add_span_processor(span_processor)


__all__ = ["setup_logging", "get_logger", "setup_tracing"]
