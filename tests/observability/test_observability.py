from __future__ import annotations

import importlib
from typing import Iterable

import pytest

_OTEL_ENV_FLAGS = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_TRACES_EXPORTER",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_METRICS_EXPORTER",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    "OTEL_LOGS_EXPORTER",
)


def _reload_module():
    import app.observability as observability

    return importlib.reload(observability)


def _clear_env(monkeypatch, keys: Iterable[str]):
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_configure_observability_without_env(monkeypatch):
    _clear_env(monkeypatch, _OTEL_ENV_FLAGS)
    module = _reload_module()

    assert module.configure_observability() is False


def test_configure_tracing_with_env(monkeypatch):
    pytest.importorskip("opentelemetry.sdk.trace")
    pytest.importorskip("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")

    _clear_env(monkeypatch, _OTEL_ENV_FLAGS)
    module = _reload_module()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "ai-trader-tests")

    assert module.configure_tracing() is True
    # Once configured, repeated calls should short-circuit.
    assert module.configure_tracing() is True
