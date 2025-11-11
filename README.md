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

## Documentation Index

| Track | Purpose | Key docs |
|-------|---------|----------|
| How-to | Procedural steps for operations, CI/CD, testing | [Operations runbook](docs/howto/operations/runbook.md), [Daily health checklist](docs/howto/operations/health-checklist.md), [CI/CD guide](docs/howto/operations/ci-cd.md), [Testing guide](docs/howto/testing.md) |
| Reference | Canonical tables, configs, policies | [Configuration defaults](docs/reference/config.md), [Secrets & Key Vault](docs/reference/secrets.md), [Risk policy](docs/reference/risk-policy.md), [Market data schemas](docs/reference/data-schema.md) |
| Explanations | Architecture narratives and roadmap context | [Architecture overview](docs/explanations/architecture/overview.md), [Core runtime](docs/explanations/architecture/core-runtime.md), [Backtesting](docs/explanations/architecture/backtesting.md), [Operations roadmap](docs/explanations/operations/roadmap.md) |
| Tutorials | Guided labs for new contributors | [Run a breakout backtest](docs/tutorials/dev-backtest.md) |
| Research (private) | Future plans, internal notes | `research-docs/` (gitignored, not published) |

All documents follow the Diátaxis framework with required front matter defined in `.docs-policy.json`.

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

Available strategies (pass via `--strategy`):

- `breakout` – classic Donchian breakout with ATR trail + regime-aware sizing.
- `momentum` – trend-following using probabilistic filtered prices, velocity, and regime whitelists.
- `mean_reversion` – z-score based entries/exits that lean on calm regimes and filtered prices.

Example CLI (probabilistic momentum run with Fractional Kelly sizing):

```bash
python3 -m app.backtest.run_breakout \
  --symbol AAPL --start 2021-01-01 --strategy momentum \
  --use-probabilistic --dal-vendor alphavantage --dal-interval 5Min \
  --regime-aware-sizing --risk-agent fractional_kelly --risk-agent-fraction 0.5 \
  --debug
```

Key flags:

- `--strategy {breakout|momentum|mean_reversion}` – select the signal engine.
- `--use-probabilistic` + `--dal-*` – pull `SignalFrame` + regimes from MarketDataDAL.
- `--risk-agent fractional_kelly` – apply fractional Kelly sizing using probabilistic signals (falls back to base risk if missing data).
- `--debug`, `--debug-signals`, `--debug-entries` – dump diagnostics/CSVs.

## Operations & Observability

Use PM2 (via `ecosystem.config.cjs`) to manage the API and log rotation:

```bash
LOG_DIR=$HOME/ai_trader_logs pm2 start ecosystem.config.cjs --only ai_trader,pm2-logrotate
pm2 restart ai_trader
pm2 logs ai_trader
```

Logs rotate daily and retain seven days by default. For OpenTelemetry / Application Insights
deployment notes see `docs/howto/operations/observability.md`.

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

- `AGENTS.md` — MCP usage guidelines for coding agents.
- `docs/explanations/architecture/*` — full architecture deep dives.
- `docs/reference/*` — canonical tables, policies, and configs (see index above).

### Watchlist Sources

`app/domain/watchlist_service.py` orchestrates symbol intake. Current options:

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
