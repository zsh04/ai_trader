---
title: Phase 2 — observability and reliability
summary: Captures the telemetry surfaces, SLOs, and alerting needed for 24/5 operations.
status: current
last_updated: 2025-11-06
type: explanation
---

# Phase 2 — Observability & Reliability

Phase 2 ensures the platform is transparent, supportable, and ready for 24/5 trading once execution is enabled. The observability stack is live today and feeds both automated alerts and the Streamlit dashboards used for manual monitoring.

## Telemetry Surfaces

- **Structured Logging** – Loguru emits JSON enriched with request IDs, chat IDs (for Telegram routes), service version, and OTEL trace context. Logs flow into Azure Application Insights / Log Analytics via the App Service integration.
- **Tracing** – `opentelemetry-instrumentation-fastapi` and custom spans in the MarketDataDAL capture vendor calls, cache behaviour, and strategy execution steps. Attributes such as `vendor`, `interval`, `symbol`, `env`, and error details make trace search practical.
- **Metrics** – OTEL metrics export latency histograms, request counters, DAL fallback counts, cache hit ratio, and data freshness gauges. Dashboards in Azure Monitor and Streamlit surface these metrics alongside operational KPIs.
- **Health Probes** – `/health/live`, `/health/ready`, `/health/db`, and `/health/dal` (planned) drive App Service readiness, Azure Monitor checks, and the Runbook diagnostics flow.
- **Dashboards** – Streamlit dashboards display watchlists, probabilistic signals, and key health indicators. Azure Monitor dashboards track API latency, DAL behaviour, and vendor usage.

## Monitoring Topology

```
Application (FastAPI/DAL)
  → Loguru JSON logs ───────────────▶ App Insights / Log Analytics
  → OTEL traces & metrics ──────────▶ OTLP exporter ─▶ App Insights / Azure Monitor
  → Health endpoints (/health/*) ───▶ App Service probes & Azure Monitor
  → Streamlit dashboards────────────▶ Operators (probabilistic metrics, watchlists)
```

Optional mirrors (Grafana, Prometheus, Sentry) can be attached later without altering application code.

## SLOs & Alert Rules (initial targets)

| Indicator | Target | Alert Trigger |
|-----------|--------|---------------|
| API availability | ≥ 99.5 % monthly | 5 min window with 5xx > 2 % |
| FastAPI latency | p95 < 1.2 s | 10 min p95 > 2 s |
| DAL freshness | < 120 s drift (market hours) | Any vendor > 3 min lag |
| Postgres health | `/health/db` p95 < 150 ms | 3 consecutive failures |
| Alpaca auth | 0 401/403 bursts | ≥ 5 failures/min for 15 min |

Alerts are routed through Azure Monitor Action Groups (email/Teams) and reference runbooks stored under `docs/howto/operations/runbook.md`.

## Incident Response Flow

1. Azure Monitor fires an alert (latency, error rate, vendor failures).
2. On-call engineer opens the curated Application Insights query (pre-filtered by request ID or vendor tag).
3. Review trace spans to isolate vendor issues vs. app errors; inspect structured logs for context (env, version, retry count).
4. Use `/health/db` and planned `/health/dal?vendor=…` to validate dependencies.
5. Apply mitigate/rollback steps defined in the runbook (switch vendor, purge cache, redeploy, etc.).
6. Post-incident, record the outcome in Jira/Confluence and adjust SLO error budgets as needed.

## Remaining Work

- Emit dedicated metrics for `dal_fallback_total` and `dal_cache_hit_ratio` once risk/strategy wiring completes.
- Finish piping Streamlit telemetry tiles into Azure Monitor so operators can pivot without leaving the UI container.
- Expand alert coverage to include paper-trade order failures before Phase 4 go-live.
