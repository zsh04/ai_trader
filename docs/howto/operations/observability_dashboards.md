---
title: Router & Event Hub dashboards
doc_type: how-to
audience: intermediate
product_area: ops
last_verified: 2025-11-11
toc: true
---

# Router & Event Hub dashboards

This guide describes how to codify the Phase 3 SLO views—`router.run` latency and Event Hub consumer lag—inside Grafana (or Azure Monitor workbooks) so releases can be gated on observable signals.

## Prerequisites

1. Grafana workspace (Grafana Cloud or Azure Managed Grafana) with data sources:
   - Tempo/OTLP traces (router spans).
   - Prometheus or Mimir for OTEL metrics (e.g., `router_runs_total`).
   - Azure Monitor data source for Event Hub metrics (`EventHubsIncomingMessages`, `EventHubsOutgoingBytes`).
   - Log Analytics workspace containing the order consumer logs (used to compute lag).
2. Azure Log Analytics workspace containing consumer logs (`order_consumer`, `sweep_job_consumer`).
3. Service annotations exported via OTEL (`service.name`, `service.version`, `deployment.environment`).
4. API token with read access so CI can capture screenshots for the release packet.

## Dashboard layout

Create a new dashboard named **“Router & Event Hub Health”** with the following rows:

### 1. LangGraph latency row

- **Panel:** `router.run latency (p50/p95/p99)`
  - Query (Tempo → TraceQL):
    ```
    { service.name = "ai-trader-api" } | span.name = "router.run"
    ```
  - Use the built-in `Latency` visualization with 5 minute rate, plus the SLO threshold (1.2 s) drawn as a reference line.
- **Panel:** `router_runs_total (success rate)`
  - PromQL example:
    ```promql
    sum(rate(router_runs_total{deployment_environment="prod"}[5m])) by (strategy)
    ```
  - Display as stacked area; add a stat for total runs last hour.

### 2. Node health row

- **Table:** `router.node duration heatmap`
  - TraceQL: group by `router.node` and compute avg duration to highlight slow stages (ingest vs. publish).
- **Bar:** `Fallback reasons`
  - Derive from Log Analytics (`fallback_reason` field) or OTEL attributes to show frequency of kill-switch, DAL failure, etc.

### 3. Event Hub lag row

- **Panel:** `EH consumer lag (ms)`
  - KQL (Log Analytics):
    ```kql
    AppTraces
    | where logger_name == "order_consumer"
    | extend lag_ms = todouble(customDimensions.lag_ms)
    | summarize avg(lag_ms), max(lag_ms) by bin(TimeGenerated, 1m)
    ```
  - Overlay warn = 60 s, critical = 180 s reference bands.
- **Panel:** `EventHubsIncomingMessages vs. router_runs_total`
  - Combine Azure Monitor metric with Prometheus counter to ensure producers and consumers stay in sync.

### 4. Sweep orchestrator row

- **Panel:** `Sweep queue depth`
  - Source: Log Analytics (`sweep_registry` entries) or the `/backtests/sweeps/jobs` API via JSON data source.
  - KQL example:
    ```kql
    sweep_jobs
    | summarize queued=sum(toint(status == "queued")), running=sum(toint(status == "running")) by bin(TimeGenerated, 1m)
    ```
  - Display as stacked bars and add a stat for current queued+running counts.
- **Panel:** `Sweep throughput`
  - Derived from Grafana JSON (API) or KQL:
    ```kql
    sweep_jobs
    | where status == "completed"
    | summarize jobs=count() by bin(TimeGenerated, 1h)
    ```
  - Visualize as column chart to highlight hourly completion rate.
- **Panel:** `ETA (mins)`
  - Calculation: `avg(duration_ms)/60000 * running_jobs`. Implement via transformation panel referencing the queue depth panel or via PromQL (export `sweep_running_jobs` + `sweep_avg_duration_ms`).

### 5. Orders/fills summary row

- **Stat:** Last order timestamp (query `/orders` via Grafana JSON data source or Log Analytics).
- **Table:** Recent fills (`/fills`) to aid ops triage without leaving Grafana.

## Alerts / SLO policies

Create Grafana alert rules (or Azure Monitor alerts) tied to the panels above:

1. **Router latency warn/page**
   - Condition: p95 of `router.run` > 1.2 s for 5 minutes → Warning; p95 > 2.0 s for 5 minutes → Critical.
   - Message template: include `env`, `service.version`, trace exemplar link.
2. **Event Hub lag**
   - Warn when avg lag > 60 s for 5 minutes; page at > 180 s for 3 minutes.
3. **Consumer silence**
   - No `router_runs_total` increments for 10 minutes triggers a warning (possible orchestrator outage).
4. **Sweep backlog**
   - Queue depth > 5 for 10 minutes → Warning; > 10 for 10 minutes → Critical.
   - Additional alert for jobs stuck `running` > 20 minutes (compare `now - started_at`).
5. **Sweep failure rate**
   - If >=2 jobs report `status="failed"` within 15 minutes, page the on-call engineer.

Capture alert definitions in Terraform or Grafana JSON under `infra/grafana/alerts/` and sync IDs in `ops/alerts.md`.

### Alert reference table

| Alert | Condition | Warn/Page | Notes |
| --- | --- | --- | --- |
| Router latency | `p95(router.run)` | Warn >1.2s/5m, Page >2.0s/5m | Link to Tempo trace exemplar |
| EH lag | `avg(lag_ms)` | Warn >60s/5m, Page >180s/3m | Derived from Log Analytics |
| Consumer silence | `rate(router_runs_total)==0` | Warn if 10m idle | Helps catch stalled orchestrator |
| Sweep backlog | queued jobs count | Warn >5, Page >10 for 10m | Data from sweep registry/API |
| Sweep failure rate | failed jobs per 15m | Page if ≥2 | Use Log Analytics query |

Document alert IDs in `ops/alerts.md` (or Terraform) so we can audit drift.

## Verification checklist

1. Trigger `/router/run` (offline mode) with `publish_orders=true`; confirm the dashboard updates within 1 minute.
2. Run `scripts/order_consumer.py` locally with `LOCAL_DEV=1` and temporarily pause it to watch lag alerts fire, then resume to ensure they auto-resolve.
3. Export dashboard JSON (`grafana dashboard export`) and store under `infra/grafana/router-health.json`. Reference it in Terraform (example below) so deployments stay consistent.
4. Capture screenshots and attach them to the release notes for Phase 3 sign‑off.

## IaC / automation tips

- **Terraform dashboard import**:

  ```hcl
  resource "grafana_dashboard" "router_health" {
    config_json = file("${path.module}/router-health.json")
    message     = "AI Trader Router/EH dashboard"
    folder      = grafana_folder.ops.id
  }
  ```

- **Terraform alerts** (Grafana managed alerts): define `grafana_contact_point`, `grafana_alert_rule` referencing the panels’ query expressions.
- **Azure Monitor equivalent**: if Grafana is unavailable, replicate the same KQL/metrics in a Workbook and attach Alert Rules; store the Workbook JSON under `infra/azure-monitor/router-health.workbook.json`.
- **CI validation**: add a step to `./scripts/dev.sh lint` or a dedicated workflow to run `grafana dashboard lint` (if available) against checked-in JSON to avoid drift.

## See also

- [How to deploy observability](./observability.md)
- [Telemetry inventory](../../reference/metrics.md)
- [Operations runbook](./runbook.md)
