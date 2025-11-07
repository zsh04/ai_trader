---
title: Phase 4 — execution and risk (paper trading)
summary: Outlines the plan for wiring risk-managed strategies into Alpaca paper execution.
status: draft
last_updated: 2025-11-06
type: explanation
---

# Phase 4 — Execution & Risk (Paper trading milestone)

Execution is the next major frontier. The infrastructure exists, but we have deliberately held back paper/live order flow until the risk agent finishes and strategies beyond breakout are fully probabilistic. This document captures the intended structure and the current status.

## Target Execution Flow

```
Strategy signal → RiskManagementAgent → Order Router → Alpaca (paper)
                              │                 │
                              │                 └─▶ Postgres (orders/fills)
                              └─▶ Risk telemetry + alerts
```

1. **Signal Generation** — Strategies consume probabilistic features from the DAL.
2. **RiskManagementAgent** — Applies fractional Kelly sizing, max drawdown checks, PDT guard, symbol halts, and buying-power validation.
3. **Order Router** — `app/execution/alpaca_client.py` encapsulates REST/WebSocket interactions, retry/backoff logic, and bracket order construction.
4. **OMS Cache** — Keeps an in-memory view of orders, fills, and positions; persists to PostgreSQL.
5. **Monitoring** — Every submit/fill event emits JSON logs and OTEL spans; exposure and order reject metrics feed Azure Monitor and Streamlit dashboards.

## Current Status (November 2025)

- Breakout strategy ready to emit signals once the risk agent is complete.
- Alpaca execution adapter supports order placement, cancellation, and streaming fills; integration tests are staged but disabled.
- Database schemas for `orders`, `fills`, `positions`, and `risk_events` defined in the initial Alembic migration.
- RiskManagementAgent design finalised (fractional Kelly with drawdown guardrails), implementation pending.
- Alert rules drafted for order rejections, exposure spikes, and vendor outages.

## Outstanding Work Before Paper Trading

| Area | Tasks |
|------|-------|
| Risk Management | Implement fractional Kelly sizing, enforce per-symbol/portfolio caps, integrate PDT guard, wire alerts. |
| Strategy Integration | Connect probabilistic signal outputs to the risk agent; validate breakout/momentum behaviour under paper fills. |
| OMS Persistence | Harden order/fill upserts, add regression tests for reconciliation, surface results in Streamlit dashboard. |
| Operational Runbooks | Finalise playbooks for Alpaca auth failures, stale data, and safe-mode transitions. |
| Automation | Enable GitHub Action to deploy the execution container and schedule premarket/refresh jobs hitting `/tasks/watchlist`. |

## Safe-Mode & Fallback Concepts

- **Data degraded** → switch strategies to cached parquet inputs; alert operators.
- **Broker degraded** → exponential backoff, circuit breaker that halts new orders while allowing position monitoring, manual reset required.
- **Risk breach** → automatic “safe mode” that exits positions (if allowed) and suppresses new trades until risk metrics normalise.

The execution milestone will be considered complete when the system can paper trade for multiple weeks with the defined risk envelope and all telemetry/alerting hooks active.
