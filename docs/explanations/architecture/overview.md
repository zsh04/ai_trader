---
title: Architecture overview
summary: Snapshot of the platform’s major subsystems and how they interact.
status: current
last_updated: 2025-11-06
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
5. **Persistence layer** — PostgreSQL keeps orders/fills/backtests, and Azure Blob Storage/Parquet stores raw artefacts and vendor caches.

```
Vendors ─▶ MarketDataDAL ─▶ Probabilistic Pipeline ─▶ Strategy/Risk ─▶ Alpaca (paper/live)
                       │                         │
                       │                         └─▶ Backtest Engine + Metrics
                       └─▶ Parquet cache / Postgres metadata
```

## Related explanations

- `docs/explanations/architecture/system.md` — system snapshot and module relationships
- `docs/explanations/architecture/core-runtime.md` — live runtime data/strategy flow
- `docs/explanations/architecture/observability.md` — telemetry, SLOs, and alerting
- `docs/explanations/architecture/backtesting.md` — backtesting workflow and artefact persistence
- `docs/explanations/architecture/execution.md` — execution milestone plan
- `docs/explanations/architecture/docs-program.md` — knowledge management roadmap
- `docs/reference/database.md` — PostgreSQL schema overview
