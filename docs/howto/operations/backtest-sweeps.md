# How to run backtest parameter sweeps

## Prerequisites

- Python virtualenv with project dependencies (`./scripts/dev.sh mkvenv && ./scripts/dev.sh install`).
- Vendor credentials in `.env.dev` (Yahoo fallback works without paid keys; Alpaca/Finnhub/Alpha Vantage optional).
- Writable `artifacts/backtests/` directory (default) or override `output_dir` in the sweep YAML.

## Steps

1. **Author a sweep profile**
   - Copy `configs/backtest/momentum_sweep.yaml` and adjust:
     - `symbol`, `start`, `end`, `strategy` (`breakout|momentum|mean_reversion`).
     - `params`: lists of values to grid-search. Each combination becomes a job.
     - `dal.vendor`/`interval` if you need a specific feed.
     - `risk_agent` to enable fractional Kelly sizing.

2. **Run the sweep CLI**
   ```bash
   source .venv/bin/activate
   python -m app.backtest.sweeps --config configs/backtest/momentum_sweep.yaml
   ```
   - Jobs execute concurrently (controlled by `max_workers`).
   - Each job stores equity/trades CSVs + `summary.json` under `artifacts/backtests/<strategy>/<timestamp>/job_XXXX/`.

3. **Review summary output**
   - The runner writes `summary.jsonl` in the sweep root directory. Each line contains `{job_id, params, metrics, equity_path, prob_frame_path}`.
   - Upload or archive the sweep directory for reproducibility.

## Verification

- Inspect the Streamlit monitoring dashboard (`/ui/dashboard`) → "Backtest Sweeps" section lists the latest summaries and charts Sharpe vs. parameter sets.
- Confirm `prob_frame_path` files exist for each job (needed by Streamlit ↔ CLI replays).
- Check CI / lint: `./scripts/dev.sh lint && ./scripts/dev.sh test` should remain green after new configs.

## References

- `configs/backtest/momentum_sweep.yaml`
- `app/backtest/sweeps.py`
- `app/monitoring/dashboard.py`
