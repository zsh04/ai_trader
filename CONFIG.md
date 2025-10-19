## CONFIG.md

```markdown
# Configuration

- **Timezone**: America/Los_Angeles (PT)
- **Sessions**: PRE 04:00–09:30; REG-AM 09:30–11:30; REG-MID 11:30–14:00; REG-PM 14:00–16:00; AFT 16:00–20:00

## Watchlist (premarket) thresholds (defaults)
- price_min = 1.00; price_max = 10.00
- gap_min_pct = 5.0
- rvol_min = 3.0
- spread_max_pct_pre = 0.75
- dollar_vol_min_pre = 1_000_000
- float_max = 100_000_000 (optional)
- max_watchlist = 15

## Risk
- max_risk_per_trade = 0.01 (1%)
- daily_drawdown_halt = 0.05 (5%)
- max_concentration_manual_gate = 0.50 (50% of account value)
- max_notional_as_pct_adv = 0.5% (20-day ADV)
- pdt_guard = enabled (≤3 day trades/5 days when balance < $25k)

## Execution
- pre/after-hours: limit + bracket only
- regular: marketable limit allowed within spread cap
- slippage_budget_pct = 0.30 (configurable by session)

## Model
- signal_model: XGBoost (binary + regression head)
- regime_model: GradientBoosting or HMM
- retrain_schedule: daily after market close

All values live in `config/config.yaml` and can be overridden by env vars.