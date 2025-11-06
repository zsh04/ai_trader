# AI Trader — v1.6.6

> Modular trading intelligence platform for watchlists, signal orchestration, and risk-aware execution.

**Python:** 3.12.x  
**Stack:** FastAPI • Market Data DAL • Streamlit • PostgreSQL  
**Deploy Target:** Azure App Service (Python)  
**Author:** Zishan Malik

## Overview

- Multi-timeframe signal generation (5m → 1D) covering equities and ETFs via Alpaca.
- Autonomous session-aware agents for watchlists, sizing, journaling, and guardrails.
- Cloud-native deployment with GitHub Actions and Azure App Service.
- Structured observability via OpenTelemetry dashboards and Streamlit UI.

## Platform Capabilities

- **Scanning & Watchlists:** Premarket gap/RVOL scans with continuous refresh windows.
- **Trading Agent Suite:** Policy, sizing, execution, and journaling agents with PDT & drawdown gates.
- **Backtesting:** Breakout strategy engine with metrics, CSV exports, and debug snapshots.
- **Integrations:** Alpaca trading + market data, Alpha Vantage intraday/EOD (with Yahoo/Twelve Data fallback), Finnhub daily quotes, PostgreSQL persistence, Azure Blob storage.
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
 ├── dal/              # Market data abstraction (vendors, cache, streaming)
 ├── data/             # ETL helpers and lightweight transforms
 ├── domain/           # Watchlist models and repositories
 ├── monitoring/       # Streamlit dashboards and widgets
 ├── observability/    # OpenTelemetry configuration helpers
 ├── probability/      # Probabilistic pipeline definitions
 ├── scanners/         # Signal and watchlist generation
 ├── services/         # Application services (watchlists, orchestration)
 ├── sessions/         # Market-session calendar utilities
 ├── strats/           # Strategy implementations (breakout, momentum, etc.)
 └── tests/            # Unit, integration, and smoke tests
```

All modules are import-safe, follow snake_case for files/functions, and use structured logging via `logging.getLogger(__name__)`.

## Getting Started

1. Install Python 3.12 (see `.python-version`).
2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   # for local development / linting
   pip install -r requirements-dev.txt
   export PYTHONPATH=.
   ```

3. Create a `.env` file (copy from `.env.example`) with broker, storage, database, and market data credentials. Never check secrets into source control—production uses Key Vault references.
4. Launch the FastAPI app locally:

   ```bash
   uvicorn app.main:app --reload --port 8000
   # or
   make run
   ```

## Development Workflow

- **Lint:** `./scripts/dev.sh lint` (ruff + bandit)
- **Auto-fix style issues:** `./scripts/dev.sh fmt` (black)
- **Tests:** `./scripts/dev.sh test`
- **Create/refresh venv:** `./scripts/dev.sh mkvenv`
- **Install deps:** `./scripts/dev.sh install`

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

Logs rotate daily and retain seven days by default. For OpenTelemetry / Application Insights
deployment notes see `docs/operations/observability.md`.

## Deployment (Azure App Service)

- GitHub Actions (`.github/workflows/ci-deploy.yml`) build, test, and deploy to the configured App Service.
- App configuration lives in Azure App Settings—no `.env` files in production.

### Market Data DAL

The probabilistic data abstraction layer (`app/dal/`) consolidates vendor access, Kalman filtering, caching, and streaming:

- **Vendors:** Alpaca (HTTP + streaming), Alpha Vantage intraday + daily (falls back to Yahoo/Twelve Data when rate-limited), Finnhub daily quotes (intraday disabled until plan upgrade). Additional vendors plug in via the `VendorClient` interface.
- **Normalization:** `Bars`/`SignalFrame` schemas enforce UTC timestamps, corporate-action aware pricing, and deterministic replay.
- **Probabilistic signals:** Each fetch/stream run produces Kalman-filtered price, velocity, and state uncertainty.
- **Persistence:** Parquet snapshots stored under `artifacts/marketdata/cache/` (configurable) with optional metadata in Postgres (`market.price_snapshots`).
- **Streaming manager:** Converts Alpaca WebSocket ticks into normalized frames with automatic gap backfill via HTTP.

Set the following environment variables to activate the primary data providers (Key Vault in production):

```bash
ALPHAVANTAGE_API_KEY=...   # falls back to Yahoo/Twelve Data when rate-limited
FINNHUB_API_KEY=...        # used for daily quotes via /quote endpoint
TWELVEDATA_API_KEY=...     # optional daily/intraday backup feed
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

`app/services/watchlist_service.py` orchestrates symbol intake. Current options:

- `auto` → Alpha Vantage listings, then Finnhub, then textlist, then Twelve Data.
- `alpha` → direct pull from Alpha Vantage listings endpoint.
- `finnhub` → US common stock listing feed (subject to API tier limits).
- `textlist` → aggregates from backends listed in `TEXTLIST_BACKENDS` (e.g., `discord,signal`).
- `manual` → parses `WATCHLIST_TEXT` (comma-separated user symbols).

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

Future roadmap: expand strategy coverage (momentum, mean reversion, risk parity), add probabilistic backtest metrics, and onboard Azure Application Insights for unified telemetry.
