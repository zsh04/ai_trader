

# AI Trader — Codex AGENTS.md

## 🧭 Purpose
This file defines coding, architectural, and operational guidelines for Codex agents collaborating on the **AI Trader** project in VS Code.  
Codex should treat this document as the **single source of truth** for naming conventions, structure, and automation logic.

---

## 🏗️ Architecture Overview
The project is modular and designed for Azure deployment:
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

---

## 🧱 Naming Conventions
| Category | Rule | Example |
|-----------|------|---------|
| Files | snake_case | `breakout_backtest.py` |
| Classes | PascalCase | `EquityMetrics`, `TradeEngine` |
| Functions | snake_case (verbs preferred) | `generate_signals`, `run_backtest` |
| Constants | UPPER_CASE | `TELEGRAM_WEBHOOK_SECRET` |
| Environment Vars | Upper snake_case | `ALPACA_API_KEY`, `AZURE_STORAGE_CONN` |
| Logging Tags | short and namespaced | `[backtest:engine]`, `[telegram:router]` |

---

## 🧩 Testing & Linting
Use built-in scripts for hygiene:
```bash
# Run tests
pytest -v

# Run static analysis
ruff check .

# Auto-fix style violations
ruff --fix .
```
> 🧠 Note: Ruff linting should **not** block Git operations (pre-commit disabled).

---

## 🧪 Local Backtesting
```bash
python3 -m app.backtest.run_breakout --symbol AAPL --start 2021-01-01 --debug
```
Optional arguments:
- `--min-notional`: risk guardrail
- `--debug-entries`: snapshot event log to CSV

---

## ⚙️ Azure Deployment
- The FastAPI app runs on **Azure App Service (Python)**.
- Environment variables are configured in **App Settings**, not via `.env`.
- GitHub Actions deploy automatically on push to `main`.

**After deployment:**  
👉 Run this immediately:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url":"<APP_SERVICE_URL>/telegram/webhook","secret_token":"<TELEGRAM_WEBHOOK_SECRET>"}'
```
> Always repeat this after every deployment to re-register your Telegram bot.

---

## 🧠 Codex Agent Rules

### General
- Maintain **strict modularity**; never hardcode environment secrets.
- Every module should be import-safe (`__init__.py` clean and explicit).
- Logging must be structured (`logger = logging.getLogger(__name__)`).

### When Editing
- Add minimal, reversible commits.
- Explain **why**, not just **what** you’re changing in commit messages.
- Use f-strings and timezone-aware datetimes (`datetime.now(timezone.utc)`).

### When Creating
- Create a test alongside every new module.
- Always include basic type hints.
- Avoid circular imports — prefer dependency injection.

---

## 🧩 Commands for Codex Sandbox
For internal Codex execution context (sandbox):
```bash
# Load environment
source .venv/bin/activate
export PYTHONPATH=.

# Run dev server
uvicorn app.main:app --reload --port 8000

# Run a test backtest
python3 -m app.backtest.run_breakout --symbol NVDA --start 2022-01-01

# PM2 (production/runtime)
LOG_DIR=$HOME/ai_trader_logs pm2 start ecosystem.config.cjs --only ai_trader,pm2-logrotate
pm2 restart ai_trader
pm2 logs ai_trader   # rotated daily, 7 days retained
```

---

## 🧭 Future Enhancements
- Extend strategy suite: momentum, mean reversion, and risk parity.
- Integrate Finviz and Discord (XTrades) watchlist ingestion.
- Add probabilistic model evaluation to `backtest.metrics`.
- Add Azure Application Insights for unified telemetry.

### Watchlist Source Summary
- `manual` → reads `WATCHLIST_TEXT` for a user-defined list.
- `textlist` → aggregates backends declared in `TEXTLIST_BACKENDS` (e.g., `discord,signal`).
- `finviz` → uses the Finviz adapter `get_symbols`.
- `scanner` → not yet implemented; warns and falls back to `textlist`.

Example configuration:
```
WATCHLIST_SOURCE=manual
WATCHLIST_TEXT="AAPL, MSFT, NVDA"
TEXTLIST_BACKENDS=discord
DISCORD_SAMPLE_SYMBOLS="TSLA, SPY"
MAX_WATCHLIST=25
```

---

## 🧾 References
- [Alpaca API Docs](https://alpaca.markets/docs/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Azure App Service for Python](https://learn.microsoft.com/en-us/azure/app-service/)
