---
title: Telemetry inventory
summary: Catalog of metrics, logs, and traces currently emitted by AI Trader.
status: current
last_updated: 2025-11-08
doc_type: reference
audience: intermediate
product_area: ops
toc: true
---

# Telemetry inventory

This reference lists the signals we emit today so operators know what to query in Grafana, Azure Monitor, or App Insights. Update this file whenever we add/remove a metric/log/trace.

## Metrics

| Metric | Source | Labels | Description |
|--------|--------|--------|-------------|
| `backtest_runs_total` | OTEL (app/backtest/run_breakout.py) | `strategy`, `risk_agent`, `dal_vendor`, `dal_interval`, `use_probabilistic` | Counts individual backtest runs (CLI or API). |
| `sweep_jobs_total` | OTEL (app/backtest/sweeps.py) | `strategy`, `risk_agent`, `dal_vendor`, `dal_interval`, `job_id` | Counts parameter sweep jobs executed. |
| `AppServiceHttpRequests`, `AppServiceCpuPercentage`, etc. | Azure Monitor (App Service) | Standard | Health of API/UI Web Apps. |
| `FrontDoorRequests`, `FrontDoorOriginLatency`, etc. | Azure Monitor (Front Door) | `route`, `originGroup` | Traffic routed via AFD. |
| `EventHubsIncomingMessages`, `EventHubsThrottledRequests` | Azure Monitor (Event Hubs namespace) | `eventHubResourceId` | Throughput/errors for `ai-trader-ehns`. |
| `PGServer CPU/Storage` | Azure Monitor (PostgreSQL Flexible Server) | Standard | Database load. |

*(Pending metrics such as consumer lag, additional OTEL counters, etc., should be added after implementation.)*

## Traces / spans

| Span name | Emitted by | Key attributes | Notes |
|-----------|------------|----------------|-------|
| `backtest.run` | `app.backtest.run_breakout.run` | `strategy`, `risk_agent`, `dal_vendor`, `dal_interval`, `use_probabilistic` | Wraps each backtest execution; minimal wrapper added in Nov 2025. |
| `backtest.run` (sweep job) | `app.backtest.sweeps._execute_job` | `strategy`, `risk_agent`, `dal_vendor`, `dal_interval`, `job_id`, `use_probabilistic` | One span per sweep job. |
| FastAPI request spans | `configure_observability()` (App Service) | Standard HTTP attrs | Avaialble for `/health/*`, `/docs`, future endpoints. |
| Streamlit request spans | `ui/streamlit_app.py` via `configure_observability()` | Standard HTTP attrs | Covers `/` and `/ui/*` traffic. |

Pending spans (not yet implemented): DAL vendor fetch, probabilistic join, engine execution, Event Hub publish/consume.

## Logs

| Logger / source | Description |
|-----------------|-------------|
| `app.*` (Loguru) | Structured logs from API/backtest/DAL modules. Each request attaches `request_id`, `env`, `version`, `sha`. |
| Streamlit (`ui.streamlit`, `streamlit.runtime.*`) | UI interactions, warnings (e.g., no cached frame, API errors). |
| `azure.eventhub.*` (when SDK logging enabled) | Event Hub diagnostics (currently via CLI scripts; will expand once producers land). |
| Front Door diagnostic logs | Not yet wired (planned GH-350). |

## Endpoints (monitoring/health)

| Endpoint | Description |
|----------|-------------|
| `/health/live`, `/health/ready` | FastAPI health probes (served via Front Door at `https://<fd-host>/health/live`). |
| `/docs`, `/openapi.json`, `/redoc` | FastAPI API docs; useful for checking API availability through AFD. |
| `/` (Streamlit) | UI home page (Front Door route with `originPath=/ui/`). |
| `/ui` | UI canonical path (Front Door specific-route without originPath). |

## To-do

- Add entries once Event Hub producers/consumers emit metrics and logs.
- Document WAF/Front Door diagnostic logs once enabled.
- When OTEL spans cover DAL/strategy internals, list them above and include typical attributes/durations.
