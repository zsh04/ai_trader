---
title: "Session Model"
doc_type: reference
audience: intermediate
product_area: trading
last_verified: 2025-11-06
toc: true
---

# Session Model

## Purpose

Define temporal buckets used for tagging signals, trades, and reports. Keeps analytics consistent across backtests, live trading, and monitoring dashboards.

## Sessions

| Code | Window (PT) | Typical focus |
|------|-------------|---------------|
| PRE | 04:00–09:30 | Gap scans, liquidity checks |
| REG-AM | 09:30–11:30 | Breakout/momentum |
| REG-MID | 11:30–14:00 | Mean-reversion, reduced size |
| REG-PM | 14:00–16:00 | Closing drives |
| AFT | 16:00–20:00 | Post-close recap, retrain |

## Tagging rules

- Every `SignalFrame`, `OrderIntent`, `Fill`, and `JournalEntry` stores `session_code`.
- Trading halts or shortened days override windows; keep overrides in `config/sessions.yaml`.

## Analytics

- Performance reports split by session to detect regime drift.
- Risk guardrails adjust slippage budget and max notional by session.

## See also

- [Configuration Defaults](./config.md)
- [Backtesting architecture explanation](../explanations/architecture/backtesting.md)
