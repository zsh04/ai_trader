# AI Trader — v0.1.0
> Modular trading intelligence platform for scanning, watchlists, and strategy orchestration.

**Version:** 0.1.0  
**Python:** 3.13.x  
**Environment:** FastAPI + Alpaca + PostgreSQL + Telegram  
**Author:** Zishan Malik



# Personal AI Trading Agent (Equities/ETFs, Alpaca, MTF)

**Goal:** Fully autonomous, session-aware retail trading agent with multi-timeframe signals (5m, 15m, 1h, 4h, 1D), daily watchlist generation, pre/regular/after-hours operation, and continuous learning. Broker: **Alpaca**.

### TL;DR
- 🧠 AI for signals + reasoning + journaling + sizing + P/L mgmt
- ⏱ Sessions: PRE (04:00–09:30), REG-AM (09:30–11:30), REG-MID (11:30–14:00), REG-PM (14:00–16:00), AFT (16:00–20:00) — **America/Los_Angeles**
- 🕵️ Daily **watchlist** via premarket scans (price $1–$10, RVOL, gap%, spread checks)
- 🛡 Guardrails: ≤1% per-trade risk, **5% daily DD halt**, manual approval if order >50% of account value
- 🚢 Cloud deploy via GitHub Actions → Azure App Service or AWS ECS (container)

### Quick Start
1. Copy `.env.example` → `.env` and fill secrets.
2. `make dev` (or `python -m venv .venv && pip install -r requirements.txt`)
3. `python -m app.main --mode paper --symbol-list config/universe.yaml`
4. Open **Streamlit dashboard**: `streamlit run app/monitoring/dashboard.py`

### Core Components
- **scanners/**: premarket & intraday scanners for watchlists
- **sessions/**: session clock + per-session metrics
- **models/**: signal + regime + trainer
- **agent/**: policy rules, sizing, risk (halts, PDT, 50% AV gate), meta-agent journaling
- **execution/**: Alpaca client, order router (brackets by default)
- **monitoring/**: Streamlit dashboard + metrics exporters

### Agents

ScannerAgent: builds watchlist at 04:00 and 06:15, refreshes 09:35 / 11:30 / 13:30 / 16:05.

UniverseAgent: merges core large-caps with dynamic small-caps ($1–$10) with ADV/spread caps.

SignalAgent: MTF features (5m…1D), classification/regression outputs + confidence.

RiskAgent: enforces ≤1% risk/trade, 5% daily DD, PDT rule, 50% AV manual gate, session throttles.

ExecutionAgent: limit+bracket in PRE/AFT; marketable limits in REG; slippage monitor.

JournalAgent / EvalAgent: per-session tagging; AI summaries + weekly retros.

### Data Flow

1. Scan → create/refresh watchlist.

2. Ingest → pull/calc features per symbol per timeframe (aligned timestamps).

3. Infer → models emit intents with confidence.

4. Decide → policy checks regime, risk, and session gates.

5. Execute → route via Alpaca; attach brackets.

6. Record → trade/journal logs; metrics into dashboard.

### Storage

Data: Parquet in data/warehouse/ + cloud bucket.

Models: models/registry/ with MLflow/W&B tracking.

Logs: SQLite (storage/trader.db) + rotated text logs.


See `ARCHITECTURE.md` and `RUNBOOK.md` for details.