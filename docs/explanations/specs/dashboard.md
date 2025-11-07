---
title: Streamlit dashboard specification
summary: Covers the goals, data sources, and page layout for the operational dashboard.
status: current
last_updated: 2025-11-06
type: explanation
---

# Streamlit dashboard specification

## Goals

Operators need fast answers to three questions: “What positions/signals exist right now?”, “How are we doing across sessions?”, and “Are hidden regressions developing (data, risk, latency)?” The Streamlit dashboard surfaces those answers without digging through raw telemetry.

## Page breakdown

1. **Today** – live orders/positions, exposure vs. limits, session clock, risk agent state (safe mode, halts).
2. **Performance** – cumulative and weekly PnL versus the +$50 weekly target, drawdown curve, Sharpe, hit rate.
3. **Sessions** – per-session PnL and hit-rate bar charts, slippage and spread heatmaps to highlight market-structure issues.
4. **Watchlist** – current candidates with filters, eligibility flags, data freshness, and DAL fallback indicators.
5. **Diagnostics** – probabilistic regime mix, feature importances, error counts, DAL cache hit ratio, vendor latency.
6. **Journal** – trade list with AI-generated summaries and weekly retrospective notes.

## Data sources

- DAL parquet caches (watchlists, probabilistic signals).
- PostgreSQL tables (`trading.orders`, `trading.fills`, `trading.equity_snapshots`).
- Azure Monitor metrics (latency, 5xx rate, vendor error counters).

## Dependencies

- `app/monitoring/dashboard.py` (Streamlit app).
- `docs/howto/operations/observability.md` (telemetry plumbing).
- `docs/howto/operations/runbook.md` (operational procedures).
