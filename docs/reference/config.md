---
title: "Configuration Defaults"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-06
toc: true
---

# Configuration Defaults

## Purpose

Canonical runtime parameters that govern watchlists, risk, execution, and model refresh cadence. All values live in `config/config.yaml` and may be overridden via environment variables (see `docs/reference/secrets.md`).

## Session taxonomy

| Session | Window (PT)    | Usage |
|---------|----------------|-------|
| PRE     | 04:00–09:30    | Premarket scans, watchlist pruning |
| REG-AM  | 09:30–11:30    | Opening drive execution |
| REG-MID | 11:30–14:00    | Mean-reversion focus |
| REG-PM  | 14:00–16:00    | Closing rotation |
| AFT     | 16:00–20:00    | Post-close recaps, retraining |

## Watchlist thresholds (defaults)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `price_min` | 1.00 USD | Minimum share price considered |
| `price_max` | 10.00 USD | Upper bound for small-cap focus |
| `gap_min_pct` | 5.0% | % gap required to enter premarket list |
| `rvol_min` | 3.0× | Relative volume filter |
| `spread_max_pct_pre` | 0.75% | Spread cap for premarket entries |
| `dollar_vol_min_pre` | 1,000,000 | Minimum USD volume in premarket |
| `float_max` | 100,000,000 | Optional float guard |
| `max_watchlist` | 15 symbols | Hard cap per session |

## Risk guardrails

| Control | Value | Notes |
|---------|-------|-------|
| `max_risk_per_trade` | 1% | Fraction of equity per position |
| `daily_drawdown_halt` | 5% | Stop opening trades for remainder of day |
| `max_concentration_manual_gate` | 50% | Manual approval if allocation exceeds threshold |
| `max_notional_as_pct_adv` | 0.5% | Exposure vs 20-day ADV |
| `pdt_guard` | enabled | Enforce Pattern Day Trader limits when balance < $25k |

## Execution profile

- Pre/after-hours: limit + bracket orders only, tightened spread guard.
- Regular session: marketable limit allowed if within `spread_cap_pct` per session.
- `slippage_budget_pct`: 0.30 default, configurable per session.

## Model cadence

- Signal model: XGBoost (binary + regression head).
- Regime model: GradientBoosting or HMM (flag via `MODEL_REGIME_TYPE`).
- `retrain_schedule`: daily after market close (18:00 PT) with outputs persisted for next session.

## Overrides

- Override any key via `ENV_VAR` → `config/config.yaml` mapping.
- Use Managed Identity + Key Vault app settings for secrets; keep `.env` samples sanitized.

## See also

- [Risk Policy](./risk-policy.md)
- [Session Model](./session-model.md)
- [Secrets & Key Vault](./secrets.md)
