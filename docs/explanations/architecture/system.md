---
title: AI Trader architecture — system snapshot
summary: High-level view of how the DAL, FastAPI services, strategies, and observability pieces fit together.
status: current
last_updated: 2025-11-11
type: explanation
---

# AI Trader architecture — system snapshot (November 2025)

## Summary

AI Trader is intentionally modular: the probabilistic Market Data Data Abstraction Layer (DAL) owns ingestion, FastAPI provides the control plane, Streamlit exposes operational visibility, and strategy/risk modules sit between the DAL and Alpaca execution. The separation lets us iterate on data providers, strategy logic, and UI without forcing coordinated releases.

```
┌─────────────────┐      ┌──────────────────┐
│  Vendors/DAL    │────▶│  Core Services   │───▶ Alpaca (orders)
│  (HTTP/WS)      │     │  (FastAPI)       │      PostgreSQL
│  • Alpaca       │     │  • Watchlists    │      Blob Storage
│  • AlphaVantage │     │  • Backtests     │
│  • Yahoo/Twelve │     │  • Health/metrics│
│  • Finnhub (EOD)│     └────────┬─────────┘
└────────┬────────┘              │
         │ probabilistic bars    │ REST/WebSocket
         ▼                       ▼
┌────────────────────────────┐  ┌──────────────────────┐
│  Probabilistic Pipeline    │  │  Streamlit Dashboard │
│  • Kalman signal filtering │  │  • Watchlists        │
│  • Regime classification   │  │  • Strategy metrics  │
│  • Parquet/Postgres cache  │  │  • Operational views │
└────────┬───────────────────┘  └──────────┬──────────┘
         │ feeds strategies                │ OTEL/JSON logs
         ▼                                 ▼
┌────────────────────────────┐  ┌──────────────────────┐
│ LangGraph Router & Risk    │  │ Observability Stack  │
│ • Breakout/Momentum/MeanRev│  │ • OTEL → App Insights│
│ • Fractional Kelly sizing  │  │ • Structured logging │
│ • AEH exec.orders flows    │  │ • Azure Monitor      │
└────────────────────────────┘  └──────────────────────┘
```

## Pillars and rationale

### Market Data DAL (`app/dal/...`)
- **Why:** We need a deterministic, vendor-agnostic layer so backtests and live trading share the exact same data pipeline.
- **How:** All vendors map to canonical `Bars` and `SignalFrame` schemas; Kalman/Band-pass filtering produces probabilistic signals and regimes.
- **Status:** Alpaca (HTTP + streaming), Alpha Vantage intraday + daily with Yahoo/Twelve Data fallback, and Finnhub daily quotes are integrated. Parquet caching plus optional PostgreSQL metadata support reproducibility.

### Core services & APIs (`app/api`, `app/services`, `app/domain`)
- **Why:** The control plane exposes health, watchlists, DAL fetches, and backtests to other agents and automation.
- **How:** FastAPI routes wrap the DAL and share fallback rules. Background tasks (pending) will drive scheduled premarket scans and refresh windows.
- **Status:** Health/watchlist/backtest endpoints are live; jobs will land alongside Phase 2 completion.

### LangGraph router, strategy & risk (`app/orchestration`, `app/agent`, `app/strats`)
- **Why:** Probabilistic features must be consumed consistently and routed through deterministic guardrails (Fractional Kelly, kill-switch) before orders leave the system.
- **How:** `app/orchestration/router.py` uses LangGraph to chain ingest → priors → strategy selection → risk sizing → AEH publish/optional Alpaca execution, with per-node OTEL spans plus Event Hub telemetry.
- **Status:** Breakout, momentum, and mean-reversion all flow through the router; AEH `exec.orders` consumer persists intents to Postgres; kill-switches are live. Priors/NLP ACA services are the next enhancement.

### Execution & persistence (`app/execution`, `app/db`, `app/adapters/market`)
- **Why:** Order routing and storage must remain insulated from strategy experiments.
- **How:** Alpaca REST/WebSocket adapters encapsulate order placement and streaming quotes. PostgreSQL houses orders/fills/regime snapshots; Blob storage keeps parquet/backtest artefacts.
- **Status:** Adapters and schema exist; paper trading will go live once the risk agent is ready.

### Observability & UI (`app/observability`, `app/monitoring`, `app/logging_utils`)
- **Why:** Without consistent telemetry we cannot trust autonomous execution.
- **How:** OTEL instrumentation tags API/router spans (`router.run`, `router.node.*`) with strategy/run metadata, and Grafana dashboards track SLOs (router p95, Event Hub lag). Streamlit dashboards surface watchlists, sweeps, and router orders from the new manifest/log feeds.
- **Status:** Instrumentation is active end-to-end; remaining work is Grafana automation + alert hooks (described in the observability runbook).

### Tooling & automation (`scripts/`, GitHub Actions, Azure resources)
- **Why:** Reproducible environments and deployments keep agents trustworthy.
- **How:** `scripts/dev.sh` standardises setup. GitHub Actions run lint/test/pip-audit and deploy the API container. Secrets flow through Managed Identity + Key Vault.
- **Status:** API pipeline is live; UI/deployment automation is scheduled for Phase 6.

## References

- `docs/explanations/architecture/overview.md` — broader architectural context
- `docs/reference/database.md` — schema reference
- `docs/howto/operations/observability.md` — how to operate telemetry
