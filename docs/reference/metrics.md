---
title: Telemetry inventory
summary: Catalog of metrics, logs, and traces currently emitted by AI Trader.
status: current
last_updated: 2025-11-11
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
| `router_runs_total` | OTEL counter (`app.telemetry.router`) | `strategy`, `symbol`, `run_id` | Increments for every LangGraph router invocation (API or CLI harness). |
| `backtest_runs_total` | OTEL (app/backtest/run_breakout.py) | `strategy`, `risk_agent`, `dal_vendor`, `dal_interval`, `use_probabilistic` | Counts individual backtest runs (CLI or API). |
| `sweep_jobs_total` | OTEL (app/backtest/sweeps.py) | `strategy`, `risk_agent`, `dal_vendor`, `dal_interval`, `job_id` | Counts parameter sweep jobs executed. |
| `eh_consumer_lag_ms` | Log-based metric (order consumer) | `event_hub`, `partition` | Derived from `scripts/order_consumer.py` logs; measures difference between now and `event.enqueued_time`. Feed into Grafana SLO panels/alerts. |
| `AppServiceHttpRequests`, `AppServiceCpuPercentage`, etc. | Azure Monitor (App Service) | Standard | Health of API/UI Web Apps. |
| `FrontDoorRequests`, `FrontDoorOriginLatency`, etc. | Azure Monitor (Front Door) | `route`, `originGroup` | Traffic routed via AFD. |
| `EventHubsIncomingMessages`, `EventHubsThrottledRequests` | Azure Monitor (Event Hubs namespace) | `eventHubResourceId` | Throughput/errors for `ai-trader-ehns`. |
| `PGServer CPU/Storage` | Azure Monitor (PostgreSQL Flexible Server) | Standard | Database load. |

## Traces / spans

| Span name | Emitted by | Key attributes | Notes |
|-----------|------------|----------------|-------|
| `router.run` | `app.orchestration.router.run_router` | `symbol`, `strategy`, `run_id` | Parent span for LangGraph orchestration; enforces 1.2s p95 budget. |
| `router.node.*` | `app.orchestration.nodes` | `router.node`, `symbol`, `strategy` | Child spans per node (`ingest_frame`, `infer_priors`, `risk_size`, `publish_order`, `execute_order`). |
| `backtest.run` | `app.backtest.run_breakout.run` | `strategy`, `risk_agent`, `dal_vendor`, `dal_interval`, `use_probabilistic` | Wraps each backtest execution. |
| `backtest.run` (sweep job) | `app.backtest.sweeps._execute_job` | `strategy`, `risk_agent`, `dal_vendor`, `dal_interval`, `job_id`, `use_probabilistic` | One span per sweep job. |
| FastAPI request spans | `configure_observability()` (App Service) | Standard HTTP attrs | Available for `/health/*`, `/docs`, `/router/*`, `/orders`, `/fills`, etc. |
| Streamlit request spans | `ui/streamlit_app.py` via `configure_observability()` | Standard HTTP attrs | Covers `/` and `/ui/*` traffic; new router panels render span-derived KPIs. |

## Logs

| Logger / source | Description |
|-----------------|-------------|
| `app.*` (Loguru) | Structured logs from API/backtest/DAL modules. Each request attaches `request_id`, `env`, `version`, `sha`. |
| Streamlit (`ui.streamlit`, `streamlit.runtime.*`) | UI interactions, warnings (e.g., no cached frame, API errors). |
| `order_consumer` / `azure.eventhub.*` | Event Hub diagnostics + consumer logs (partition, sequence, lag). |
| Front Door diagnostic logs | Not yet wired (planned GH-350). |

## Endpoints (monitoring/health)

| Endpoint | Description |
|----------|-------------|
| `/health/live`, `/health/ready` | FastAPI health probes (served via Front Door at `https://<fd-host>/health/live`). |
| `/docs`, `/openapi.json`, `/redoc` | FastAPI API docs; useful for checking API availability through AFD. |
| `/` (Streamlit) | UI home page (Front Door route with `originPath=/ui/`). |
| `/ui` | UI canonical path (Front Door specific-route without originPath). |
| `/orders`, `/fills` | API listings of Event Hub-derived orders/fills for UI/API consumers. |

## To-do

- Document WAF/Front Door diagnostic logs once enabled.
- When OTEL spans cover DAL/strategy internals beyond router nodes, expand the table with duration targets.
