---
title: "Tutorial: Run a breakout backtest"
doc_type: tutorial
audience: beginner
product_area: backtest
last_verified: 2025-11-06
toc: true
---

# Tutorial: Run a breakout backtest

Follow this guided lab to bootstrap the development environment, wire market data credentials, and execute the breakout strategy backtest end to end.

## Goal

Produce a breakout backtest report for `AAPL` (starting 2021-01-01) with probabilistic sizing enabled, storing artifacts locally.

## Prerequisites

- macOS/Linux shell with Git and Python 3.12 installed.
- Clone of this repository.
- Optional: Alpha Vantage API key (for live data pulls); otherwise the suite falls back to bundled fixtures.

## Steps

1. **Create the virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt -r requirements-dev.txt
   ```
2. **Copy environment template**
   ```bash
   cp .env.example .env
   ```
   Populate the following keys if you intend to hit real vendors:
   - `ALPHAVANTAGE_API_KEY`
   - `TWELVEDATA_API_KEY`
   - `FINNHUB_API_KEY`
3. **Seed the database (optional)**
   - If you want Postgres-backed artifacts, point `DATABASE_URL` at your dev instance and run `alembic upgrade head`.
   - Otherwise, the backtest stores snapshots under `artifacts/backtests/`.
4. **Run lint/tests (sanity check)**
   ```bash
   ./scripts/dev.sh lint
   ./scripts/dev.sh test
   ```
5. **Execute the breakout CLI**
   ```bash
   python -m app.backtest.run_breakout \
     --symbol AAPL \
     --start 2021-01-01 \
     --use-probabilistic \
     --regime-aware-sizing \
     --dal-vendor alphavantage \
     --debug
   ```
   Flags explained:
   - `--use-probabilistic` streams Kalman-filtered features from the MarketDataDAL cache.
   - `--regime-aware-sizing` scales exposure using the latest `RegimeAnalysisAgent` output.
   - `--debug` emits CSV snapshots for each signal in `artifacts/backtests/<timestamp>/`.
6. **Inspect artifacts**
   - Metrics JSON: `artifacts/backtests/<timestamp>/metrics.json`
   - Orders CSV: `artifacts/backtests/<timestamp>/orders.csv`
   - Probabilistic traces: `artifacts/backtests/<timestamp>/signals.parquet`
7. **Clean up** (optional)
   ```bash
   deactivate
   rm -rf .venv
   ```

## Troubleshooting

- Missing API key → the DAL emits warnings and falls back to cached fixtures; rerun with valid keys to compare results.
- `sqlite://` Alembic errors → ensure `DATABASE_URL` points to Postgres or remove the `alembic` step.
- Slow fetches → set `DAL_CACHE_ONLY=1` to replay existing parquet snapshots.

## Next steps

- Swap symbols or extend the date window to stress-test other tickers.
- Integrate the Streamlit UI (coming soon) to visualize breakout results interactively.
- Commit improvements and update the `docs/tutorials/` index when adding new guided labs.
