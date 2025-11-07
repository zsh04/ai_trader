---
title: Phase 3 — backtesting and research
summary: Details how the probabilistic DAL feeds the backtest harness for reproducible strategy evaluation.
status: current
last_updated: 2025-11-06
type: explanation
---

# Phase 3 — backtesting and research

## Purpose

Backtests must exercise the identical DAL + probabilistic filters used in production; otherwise we cannot trust performance metrics. Phase 3 captures how we achieve that parity.

## Current Backtest Pipeline

1. **Data Fetch**
   - `MarketDataDAL.fetch_bars()` pulls historical bars from the selected vendor (Alpaca, Alpha Vantage + fallback, Finnhub daily quotes).
   - Fetched bars are normalised and cached to Parquet so that repeated sweeps reuse the same dataset.

2. **Probabilistic Feature Generation & Persistence**
   - `SignalFilteringAgent` runs Kalman filtering, EMA, and Butterworth smoothing to produce `SignalFrame` objects.
   - `RegimeAnalysisAgent` labels each timestamp (e.g., `trend_up`, `sideways`) with uncertainty scores.
   - Joined frames are persisted via `app.probability.storage.persist_probabilistic_frame` under `artifacts/probabilistic/frames`, so CLI runs, Streamlit and sweeps can all reuse the identical enriched DataFrame.

3. **Strategy Evaluation**
   - Strategies receive the probabilistic frames along with optional raw OHLCV. Breakout, momentum, and mean-reversion are all available under `app/strats/` and selectable via the new `--strategy` flag.
   - The CLI automatically enables DAL fetches for strategies that require probabilistic inputs and records the final merged frame for downstream consumers.
   - Orders are simulated via the in-memory broker model (`app/backtest/engine.py`), accounting for slippage, fees, and bracket logic. Risk agents (e.g., `--risk-agent fractional_kelly --risk-agent-fraction 0.5`) further modulate the base risk fraction when probabilistic data is present.

4. **Metrics & Persistence**
   - Metrics (`Sharpe`, `Sortino`, drawdown, hit rate, Kelly efficiency) are computed and written to the `backtest` schema in PostgreSQL.
   - Artefacts (CSV equity curves, JSON configs) are registered against Blob storage paths for traceability.

```
DAL fetch → SignalFilteringAgent → Strategy runner → BrokerSim → Metrics → Reports
```

## Running backtests

- CLI: `python -m app.backtest.run_breakout --symbol AAPL --start 2021-01-01 --end 2021-03-01 --strategy momentum --use-probabilistic --dal-vendor yahoo --dal-interval 1Day --risk-agent fractional_kelly --risk-agent-fraction 0.4`
- Programmatic usage: orchestrate `fetch_probabilistic_batch`, call `join_probabilistic_features`, then invoke the target strategy helper.
- Sweeps: `python -m app.backtest.sweeps --config configs/backtest/momentum_sweep.yaml` spins up concurrent jobs using the cached DAL frames, writes per-job JSON/CSV artefacts, and emits a consolidated `summary.jsonl` for dashboards.

## Dashboards / Reporting

- The Streamlit monitoring dashboard (`app/monitoring/dashboard.py`, served at `/ui/dashboard`) ingests the latest `summary.jsonl` files from `artifacts/backtests/…` and visualises Sharpe vs. parameter combinations under a "Backtest Sweeps" panel.
- Equity/trade CSVs remain available per job for deeper notebook analysis, while probabilistic frame paths let the `/ui` console replay signals without re-hitting vendors.

## Current status

- Probabilistic DAL integrated end-to-end (bars + signals + regimes) with cached frames reusable by Streamlit and sweeps.
- Breakout, momentum, and mean-reversion strategies selectable via CLI/Streamlit, each sourcing the DAL output.
- Fractional Kelly risk agent wired behind a flag for deterministic sizing adjustments.
- Backtest outputs persisted to both Parquet (raw results) and PostgreSQL (summary metrics).

## Outstanding tasks

- Add additional regime-specific diagnostics to the momentum / mean-reversion strategies and continue broad regression coverage.
- Automate parameter sweeps with result persistence under `artifacts/backtests/<strategy>/<timestamp>/`.
- Add reporting glue to Streamlit so probabilistic backtest results appear alongside live dashboards.
