# Phase 2: Observability

This phase focuses on enhancing system reliability, transparency, and enabling data-driven insights through comprehensive observability.

```mermaid
graph TD
  %% Application Components emit logs, metrics, and events
  subgraph Application Components
    A1[Core Runtime]
    A2[Backtest]
    A3[Telegram Bot]
    A4[Scheduler]
  end

  %% Logs flow into Logger and then Central Log Store
  subgraph Logging
    L1[Logger (Loguru)]
    L2[Central Log Store (Blob Storage / Azure Log Analytics)]
  end

  %% Metrics flow into Prometheus-compatible Collector and then Grafana Dashboards
  subgraph Metrics
    M1[Prometheus-compatible Collector]
    M2[Grafana Dashboards (custom themes)]
  end

  %% Events and Errors flow into Telegram Alerts and then Ops Channel
  subgraph Alerts
    E1[Telegram Alerts]
    E2[Ops Channel]
  end

  %% Data flow connections
  A1 -->|Logs| L1
  A2 -->|Logs| L1
  A3 -->|Logs| L1
  A4 -->|Logs| L1

  L1 --> L2

  A1 -->|Metrics| M1
  A2 -->|Metrics| M1
  A3 -->|Metrics| M1
  A4 -->|Metrics| M1

  M1 --> M2

  A1 -->|Events/Errors| E1
  A2 -->|Events/Errors| E1
  A3 -->|Events/Errors| E1
  A4 -->|Events/Errors| E1

  E1 --> E2

  %% Side annotations
  classDef annotation fill:#f9f,stroke:#333,stroke-width:1px,color:#000,font-style:italic;

  DataRetention[Data Retention: Blob Storage]:::annotation
  Visualization[Visualization: Grafana]:::annotation
  Alerting[Alerting: Telegram]:::annotation

  L2 --- DataRetention
  M2 --- Visualization
  E1 --- Alerting
```

%% PHASE 2 — OBSERVABILITY (Monitoring, Logs, Metrics, Tracing, Health, Alerts)
%% ---------------------------------------------------------------------------
%% This Mermaid file captures the target-state observability architecture for ai_trader.
%% Scope: structured logging, metrics, tracing, health probes, dashboards, alerting,
%% SLOs/error budgets, and runbook-oriented incident flow.

%% =============================
%% 1) Component/Flow Topology
%% =============================
flowchart TD
  %% App Layer
  subgraph APP[Application Layer]
    A1[FastAPI Uvicorn/Gunicorn\napp.main:app]
    A2[Telegram Router\n/app/wiring/telegram_router.py]
    A3[Adapters\nHTTP, Alpaca, Yahoo, DB]
    A4[Health Endpoints\n/health, /health/live, /health/db, /health/ready, /version]
  end

  %% Telemetry SDKs
  subgraph SDKS[In-Process Telemetry]
    S1[Structured Logging\n(Loguru -> JSON)]
    S2[Metrics\n(OpenTelemetry Metrics)]
    S3[Tracing\n(OpenTelemetry Traces)]
    S4[Correlation IDs\n(X-Request-ID, chat_id)]
  end

  %% Collectors / Agents
  subgraph COLLECT[Collectors / Agents]
    C1[OTel Exporter (OTLP/HTTP)]
    C2[App Insights SDK Bridge]
  end

  %% Platform Observability
  subgraph AZURE[Azure Observability]
    D1[Application Insights\n(Logs + Traces + Metrics)]
    D2[Log Analytics Workspace]
    D3[Azure Monitor Metrics]
    D4[Dashboards\n(App Insights + Azure Monitor)]
    D5[Alerts & Action Groups\n(Email, Teams/Webhook)]
  end

  %% External Destinations (optional)
  subgraph EXT[Optional Extensions]
    E1[Grafana (Azure Managed)]
    E2[Prometheus (Managed)]
    E3[Sentry or Honeycomb]
  end

  %% Data Stores / Dependencies
  subgraph DATA[Data Dependencies]
    DB[(Azure PostgreSQL Flexible)]
    ALPACA[(Alpaca Data API)]
    YF[(Yahoo Finance)]
  end

  %% Users
  subgraph OPS[Ops / Stakeholders]
    U1[Runbooks & Playbooks]
    U2[On-call Engineer]
    U3[Bot Users]
  end

  %% Edges: App -> SDKs
  A1 --> S1
  A1 --> S2
  A1 --> S3
  A2 --> S1
  A2 --> S3
  A4 --> S2

  %% Edges: SDKs -> Collectors
  S1 --> C2
  S2 --> C1
  S3 --> C1
  S4 -. adds context .- S1
  S4 -. adds context .- S3

  %% Edges: Collectors -> Azure
  C1 --> D1
  C2 --> D1
  D1 --> D2
  D1 --> D3
  D1 --> D4
  D1 --> D5

  %% Optional mirrors to external tools
  D1 -. mirrored charts .-> E1
  D3 -. metrics scrape .-> E2
  S1 -. optional error stream .-> E3

  %% App Dependencies
  A3 --> DB
  A3 --> ALPACA
  A3 --> YF

  %% Health & Users
  A4 -->|/health/* JSON| U3
  D5 -->|Notify| U2
  U2 -->|Follow Runbook| U1

  %% Notes
  classDef primary fill:#164,stroke:#0a2,color:#fff
  classDef accent fill:#0a5,stroke:#063,color:#fff
  class A1,A2,A3,A4 primary
  class D1,D4 accent

%% Key Logging Fields (structured JSON):
%%  ts, level, logger, msg, scope, method, url, status, latency_ms,
%%  chat_id, user_id, req_id, component, attempt, success, error, env, version


%% =====================================
%% 2) Incident & Alerting Sequence Flow
%% =====================================
sequenceDiagram
  autonumber
  participant Bot as Telegram Bot User
  participant API as ai_trader API
  participant OTel as OTel Exporter
  participant APM as Azure App Insights
  participant AM as Azure Monitor + Alerts
  participant OnCall as On-call Engineer

  Bot->>API: /watchlist
  API->>API: Process request (handlers, adapters)
  API->>APM: Trace span start (route=/telegram/webhook)
  API->>OTel: Emit metrics (latency_ms, errors_total)
  API->>APM: Send logs (structured JSON)
  API->>APM: End span (status_code)
  APM-->>AM: Kusto queries + metric rules evaluated
  AM-->>OnCall: Alert fired (Latency p95>2s OR 5xx rate>2%)
  OnCall->>APM: Jump to trace sample + logs (req_id)
  OnCall->>API: Run /health/db & /version (diagnostics)
  OnCall->>API: Apply runbook: rollback or config hotfix
  API->>APM: Recovery signals (errors drop, p95 normal)
  AM-->>OnCall: Auto-resolve alert


%% ===========================================
%% 3) SLOs / Error Budgets (Policy Snapshot)
%% ===========================================
%% - Availability SLO (API): 99.5% monthly; Global 5xx rate < 0.5%
%% - Latency SLO (Telegram webhook): p95 < 1.2s, p99 < 2.0s
%% - DB Readiness: /health/db latency < 150ms p95
%% - Data Freshness (market data snapshot): < 2m behind during market hours
%% - Error Budget burn alerts: warn at 25%, page at 50% within any 24h window


%% ==================================
%% 4) Alert Rules (Initial Defaults)
%% ==================================
%% - HTTP 5xx rate > 2% for 10m (route label, env)
%% - Webhook latency p95 > 2s for 10m (env=prod)
%% - DB ping failures > 3 consecutive (env=prod)
%% - Alpaca HTTP 401/403 spikes > 5/min for 15m
%% - Telegram send failures > 3/min for 10m
%% - App restart flapping (>=4 restarts in 30m)


%% ======================================
%% 5) Dashboards (tiles you should pin)
%% ======================================
%% - API Overview: RPS, p50/p95/p99 latency (by route), 4xx/5xx, top errors
%% - Telegram Ops: cmd counts, success ratio, message sizes, retries
%% - Market Data: Alpaca/YF request volume, error rate, freshness lag
%% - DB Panel: connections, query latency, pings, timeout count
%% - Infra: CPU %, Memory, GC time, Worker restarts


%% ==============================================
%% 6) Implementation Notes (quick checklist)
%% ==============================================
%% [ ] Ensure opentelemetry-instrumentation-fastapi & requests installed
%% [ ] Configure OTLP exporter endpoint (App Insights or OTel collector)
%% [ ] Emit JSON logs (Loguru -> stdout), include req_id & chat_id
%% [ ] Map log levels to App Insights severity (DEBUG->Verbose, etc.)
%% [ ] Add /health/* endpoints (already done) and mark no-auth
%% [ ] Tag all telemetry with env, version, region
%% [ ] Wire alert rules in Azure Monitor with Action Group
%% [ ] Document runbooks for top 5 incidents in /documents/runbooks