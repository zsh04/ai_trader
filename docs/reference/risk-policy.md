---
title: "Risk Policy"
doc_type: reference
audience: advanced
product_area: risk
last_verified: 2025-11-06
toc: true
---

# Risk Policy

## Purpose

Hard limits enforced by RiskManagementAgent, MarketDataDAL consumers, and execution adapters.

## Core limits

| Control | Value | Enforcement |
|---------|-------|-------------|
| Per-trade risk | ≤ 1% of equity | Kelly fraction capped + order sizing |
| Daily drawdown | 5% | Halt new entries remainder of day |
| Concentration gate | 50% of account value | Manual approval required |
| ADV exposure | 0.5% of 20-day ADV per symbol | Skip trade if exceeded |
| PDT guard | Enabled when balance < $25k | Track intraday round trips |
| Kill switch | Manual + auto trigger | Infra/data anomalies halt trading |

## Session-specific rules

- Extended hours: limit + bracket orders only; reduced notional.
- Regular session: marketable limit allowed if spread < `spread_cap_pct`.
- Slippage budget: 0.30 default; dynamic adjustments per regime volatility.

## Compliance hooks

- Every `OrderIntent` logs evaluation metadata: `risk_reason`, `kelly_fraction`, `p_adjusted`.
- Guardrail violations emit structured OTEL logs + alerts.

## See also

- [Configuration Defaults](./config.md)
- [Secrets & Key Vault](./secrets.md)
- [Risk agent design](../explanations/architecture/backtesting.md#risk)
