# AI Trader — v1.5.5

> Modular trading intelligence platform for watchlists, signal orchestration, and risk-aware execution.

**Python:** 3.12.x  
**Stack:** FastAPI • Alpaca • PostgreSQL • Telegram  
**Deploy Target:** Azure App Service (Python)  
**Author:** Zishan Malik

## Overview

- Multi-timeframe signal generation (5m → 1D) covering equities and ETFs via Alpaca.
- Autonomous session-aware agents for watchlists, sizing, journaling, and guardrails.
- Cloud-native deployment with GitHub Actions and Azure App Service.
- Structured observability and Telegram notifications for trade and system health.

## Platform Capabilities

- **Scanning & Watchlists:** Premarket gap/RVOL scans with continuous refresh windows.
- **Trading Agent Suite:** Policy, sizing, execution, and journaling agents with PDT & drawdown gates.
- **Backtesting:** Breakout strategy engine with metrics, CSV exports, and debug snapshots.
- **Integrations:** Alpaca market/execution data, PostgreSQL persistence, Azure Blob storage, Telegram bot.
- **Probabilistic Market Data Layer:** Unified DAL that normalizes Alpaca, Alpha Vantage, and Finnhub feeds (HTTP + WebSocket) and emits Kalman-filtered probabilistic signals with parquet/Postgres persistence.

## Architecture

```
app/
 ├── adapters/         # Data persistence and integration (Postgres, Blob)
 ├── agent/            # Risk, sizing, and trading logic modules
 ├── api/              # FastAPI endpoints and webhooks
 ├── backtest/         # Engine, metrics, strategy evaluation
 ├── core/             # Models, exceptions, utilities, time/calendar logic
 ├── features/         # Derived signals, multi-timeframe indicators
 ├── monitoring/       # Logging, telemetry, dashboards
 ├── notifiers/        # Telegram, alerts, webhooks
 ├── providers/        # Market data sources (Alpaca, Yahoo, Finviz)
 ├── scanners/         # Signal and watchlist generation
 ├── strats/           # Strategy implementations (breakout, momentum, etc.)
 ├── storage/          # Azure Blob, local caching
 ├── telemetry/        # Unified observability hooks
 └── tests/            # Unit, integration, and smoke tests
```

All modules are import-safe, follow snake_case for files/functions, and use structured logging via `logging.getLogger(__name__)`.

## Getting Started

1. Install Python 3.12 (see `.python-version`).
2. Create a virtual environment and install deps:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   export PYTHONPATH=.
   ```

3. Create a `.env` file in the repo root with broker, storage, database, Telegram, and market data credentials (see `app/settings.py`). Never check secrets into source control.
4. Launch the FastAPI app locally:

   ```bash
   uvicorn app.main:app --reload --port 8000
   # or
   make run
   ```

## Development Workflow

- **Lint:** `ruff check .`
- **Auto-fix style issues:** `ruff --fix .`
- **Tests:** `pytest -v` or `make test`
- **Formatted build:** `make format`
- **Scripted helpers:** `./scripts/dev.sh lint|fmt|test|run|pm2-up|webhook-set`

Always add type hints, avoid circular imports, and keep modules composable. New features must include matching tests under `tests/`.

## Backtesting

Run the breakout engine with optional risk guardrails and debug exports:

```bash
python3 -m app.backtest.run_breakout --symbol AAPL --start 2021-01-01 --debug
# optional
#   --min-notional <USD>
#   --debug-entries   # emit CSV snapshots for inspection
#   --use-probabilistic --dal-vendor finnhub --regime-aware-sizing
#     # pull MarketDataDAL signals/regimes and scale risk via latest regime snapshot
```

## Operations & Observability

Use PM2 (via `ecosystem.config.cjs`) to manage the API and log rotation:

```bash
LOG_DIR=$HOME/ai_trader_logs pm2 start ecosystem.config.cjs --only ai_trader,pm2-logrotate
pm2 restart ai_trader
pm2 logs ai_trader
```

Logs rotate daily and retain seven days by default.

## Deployment (Azure App Service)

- GitHub Actions (`.github/workflows/ci-deploy.yml`) build, test, and deploy to the configured App Service.
- App configuration lives in Azure App Settings—no `.env` files in production.
- After every deployment, reset the Telegram webhook:

  ```bash
  curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
       -H "Content-Type: application/json" \
       -d '{"url":"<APP_SERVICE_URL>/telegram/webhook","secret_token":"<TELEGRAM_WEBHOOK_SECRET>"}'
  ```

### Market Data DAL

The probabilistic data abstraction layer (`app/dal/`) consolidates vendor access, Kalman filtering, caching, and streaming:

- **Vendors:** Alpaca (HTTP + streaming), Alpha Vantage (HTTP), Finnhub (HTTP + streaming). Additional vendors plug in via the `VendorClient` interface.
- **Normalization:** `Bars`/`SignalFrame` schemas enforce UTC timestamps, corporate-action aware pricing, and deterministic replay.
- **Probabilistic signals:** Each fetch/stream run produces Kalman-filtered price, velocity, and state uncertainty.
- **Persistence:** Parquet snapshots stored under `artifacts/marketdata/cache/` (configurable) with optional metadata in Postgres (`market_data_snapshots`).
- **Streaming manager:** Converts Alpaca/Finnhub WebSocket ticks into normalized frames with automatic gap backfill via HTTP.

Set the following environment variables to activate non-Alpaca vendors:

```bash
ALPHAVANTAGE_API_KEY=...   # retrieved from https://www.alphavantage.co/
FINNHUB_API_KEY=...        # retrieved from https://finnhub.io/
```

Instantiate the DAL from your module or notebook:

```python
from app.dal.manager import MarketDataDAL

dal = MarketDataDAL()
batch = dal.fetch_bars("AAPL", interval="1Min", vendor="finnhub",
                       start=..., end=...)
print(batch.bars.symbol, len(batch.signals), batch.regimes[-1].regime)

# async streaming example
async for payload in dal.stream_bars(["AAPL", "MSFT"], vendor="alpaca"):
    print(payload.signal.price, payload.regime.regime)
```

Unit/regression tests covering the DAL live under `tests/dal/`. Running `pytest -q` exercises both the fetch and streaming pipelines (using stub vendors for deterministic behavior).

## Additional Docs

- `ARCHITECTURE.md` — design deep dive
- `RUNBOOK.md` — operational checklists and incident flows
- `AGENTS.md` — coding conventions and agent collaboration guide

### Watchlist Sources

- `manual` → parses `WATCHLIST_TEXT` (comma-separated user symbols).
- `textlist` → aggregates from backends listed in `TEXTLIST_BACKENDS` (e.g., `discord,signal`).
- `finviz` → pulls via the Finviz screener wrapper.
- `scanner` → reserved; currently warns and falls back to `textlist`.

Example env:

```
WATCHLIST_SOURCE=manual
WATCHLIST_TEXT="AAPL, MSFT, NVDA"
TEXTLIST_BACKENDS=discord
DISCORD_SAMPLE_SYMBOLS="TSLA, SPY"
MAX_WATCHLIST=25
```

### Watchlist persistence

- **Local fallback (default):** JSON under `./data/watchlists/{bucket}/{ts}.json`
- **Azure Blob (optional):**
  - `AZURE_BLOB_CONNECTION_STRING`
  - `AZURE_BLOB_CONTAINER`
- **Postgres index (optional):**
  - `DATABASE_URL` (requires `psycopg2`; otherwise index is skipped)

Future roadmap: expand strategy coverage (momentum, mean reversion, risk parity), integrate Finviz/Discord watchlists, add probabilistic backtest metrics, and onboard Azure Application Insights for unified telemetry.
