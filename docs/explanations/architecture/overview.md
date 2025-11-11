---
title: Architecture overview
summary: Snapshot of the platform’s major subsystems and how they interact.
status: current
last_updated: 2025-11-10
type: explanation
---

# Architecture overview (November 2025)

## Purpose

This overview explains how the major subsystems fit together and why the platform is segmented the way it is. Use it when onboarding new contributors or evaluating cross-cutting changes.

## Subsystems at a glance

1. **Market Data DAL** — normalises all vendor data (Alpaca, Alpha Vantage with Yahoo/Twelve Data fallback, Finnhub daily quotes) and emits probabilistic `SignalFrame`/regime data that both backtests and live strategies consume.
2. **Core services (FastAPI)** — surfaces watchlists, DAL helpers, health probes, and backtests; future cron-style jobs will orchestrate premarket refreshes.
3. **Strategy & risk modules** — convert probabilistic features into orders (breakout live today; momentum/mean-reversion + fractional Kelly sizing in progress) while guarding against exposure breaches.
4. **Observability & dashboards** — OTEL + Loguru telemetry flow into Azure Monitor; Streamlit dashboards provide human-friendly visibility.
5. **Orchestration layer (LangGraph)** — new `app/orchestration/router.py` drives ingest → priors → strategy pick → Fractional Kelly sizing → AEH order intents with deterministic fallbacks and a CLI harness (`python -m app.orchestration.router --runs 100`) for latency tests.
6. **Eventing & edge** — Azure Event Hubs (`ai-trader-ehns`) handles bars/signals/regimes/backtest job streams; Azure Front Door terminates public traffic and routes `/` to Streamlit UI and `/health/*`, `/docs*` etc. to FastAPI before it hits the locked-down App Services.
7. **Persistence layer** — PostgreSQL keeps orders/fills/backtests, and Azure Blob Storage/Parquet stores raw artefacts and vendor caches (including EH checkpoints).

```
Vendors ─▶ MarketDataDAL ─▶ Probabilistic Pipeline ─▶ Strategy/Risk ─▶ Alpaca (paper/live)
                       │                         │
                       │                         └─▶ Backtest Engine + Metrics ─▶ Event Hubs (jobs)
                       └─▶ Parquet cache / Postgres metadata ─▶ Event Hubs (bars/signals/regimes)

Azure Front Door (fd-ai-trader) routes `/` and `/ui/*` to the Streamlit Web App and `/health/*`, `/docs*`, `/openapi.json`, etc. to FastAPI while App Services only allow the Front Door backend service tag.
```

## Related explanations

- `docs/explanations/architecture/system.md` — system snapshot and module relationships
- `docs/explanations/architecture/core-runtime.md` — live runtime data/strategy flow
- `docs/explanations/architecture/observability.md` — telemetry, SLOs, and alerting
- `docs/explanations/architecture/backtesting.md` — backtesting workflow and artefact persistence
- `docs/explanations/architecture/execution.md` — execution milestone plan
- `docs/explanations/architecture/docs-program.md` — knowledge management roadmap
- `docs/reference/database.md` — PostgreSQL schema overview
