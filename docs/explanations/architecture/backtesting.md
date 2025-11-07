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

2. **Probabilistic Feature Generation**
   - `SignalFilteringAgent` runs Kalman filtering, EMA, and Butterworth smoothing to produce `SignalFrame` objects.
   - `RegimeAnalysisAgent` labels each timestamp (e.g., `trend_up`, `sideways`) with uncertainty scores.

3. **Strategy Evaluation**
   - Strategies receive the probabilistic frames along with optional raw OHLCV. Breakout is active; momentum/mean-reversion harnesses are staged under `app/strats/`.
   - Orders are simulated via the in-memory broker model (`app/backtest/engine.py`), accounting for slippage, fees, and bracket logic.

4. **Metrics & Persistence**
   - Metrics (`Sharpe`, `Sortino`, drawdown, hit rate, Kelly efficiency) are computed and written to the `backtest` schema in PostgreSQL.
   - Artefacts (CSV equity curves, JSON configs) are registered against Blob storage paths for traceability.

```
DAL fetch → SignalFilteringAgent → Strategy runner → BrokerSim → Metrics → Reports
```

## Running backtests

- CLI: `python -m app.backtest.run_breakout --symbol AAPL --start 2021-01-01 --use-probabilistic`
- Programmatic usage: orchestrate `fetch_probabilistic_batch` and pass merged DataFrames into strategy helpers.
- Parameter sweeps will be managed through YAML profiles + concurrent futures (planned).

## Current status

- Probabilistic DAL integrated end-to-end (bars + signals + regimes).
- Breakout strategy validated against multiple vendors.
- Backtest outputs persisted to both Parquet (raw results) and PostgreSQL (summary metrics).

## Outstanding tasks

- Finalise momentum/mean-reversion implementations and add regression tests comparing probabilistic vs. raw feature runs.
- Automate parameter sweeps with result persistence under `artifacts/backtests/<strategy>/<timestamp>/`.
- Add reporting glue to Streamlit so probabilistic backtest results appear alongside live dashboards.
