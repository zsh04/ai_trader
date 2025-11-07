

---
title: Roadmap — personal AI trading agent
summary: Milestone-by-milestone plan for the Azure/Alpaca probabilistic trading agent.
status: current
last_updated: 2025-11-06
type: explanation
---

# Roadmap — personal AI trading agent

## Scope

- Instrument: US equities/ETFs (Phase 0–5).
- Runtime: Azure App Service (Linux), Azure Blob Storage, Azure Database for PostgreSQL, Alpaca broker.
- Sessions: PRE, REG-AM, REG-MID, REG-PM, AFT; daily watchlist with $1–$10 premarket scanner.

---

## Milestone 0 — project bootstrap (Day 0–1)
**Goals**
- Repo scaffold committed; docs in place; Azure-first config working locally.
**Deliverables**
- `README.md`, `ARCHITECTURE.md`, `CONFIG.md`, `RISK_POLICY.md`, `SESSION_MODEL.md`, `WATCHLIST_SPEC.md`, `DATA_SCHEMA.md`, `DASHBOARD_SPEC.md`, `CI_CD.md`, `RUNBOOK.md`, `CONTRIBUTING.md`, `.env.example`, `LICENSE`.
**Exit Criteria**
- `pip install -r requirements.txt` succeeds; `pre-commit`/lint pass.

---

## Milestone 1 — data & sessions (Sprint 1, ~3–4 days)
**Goals**
- Ingest historical & intraday candles from Alpaca; implement extended-hours data loader; align multi-timeframe (5m, 15m, 1h, 4h, 1D). Implement session clock & tagging.
**Work Items**
- `app/data/data_client.py` (Alpaca)
- `app/features/mtf_aggregate.py`
- `app/sessions/session_clock.py` (PT windows; PRE/REG-AM/REG-MID/REG-PM/AFT)
- Persist to **Azure Blob** (parquet) with local cache fallback
**Exit Criteria**
- CLI command writes aligned parquet to Blob; all rows contain `session` tag.

---

## Milestone 2 — premarket scanner & universe agent (Sprint 2, ~3–4 days)
**Goals**
- Build watchlist from premarket volume/gappers for $1–$10 names; merge with core liquid universe.
**Work Items**
- `app/scanners/premarket_scanner.py` (gap%, RVOL, dollar vol, spread caps, float proxy)
- `app/scanners/intraday_scanner.py` (RVOL spikes, range expansion, HOD breaks)
- `app/universe/universe_agent.py` (ADV exposure caps, spread caps)
- Write `data/watchlists/YYYY-MM-DD.json`
**Exit Criteria**
- 04:00 rough list; 06:15 finalized list; size ≤ `MAX_WATCHLIST`; persisted to Blob.

---

## Milestone 3 — baseline model & backtest harness (Sprint 3, ~4–5 days)
**Goals**
- Establish baseline signal model + rules; backtest with costs & slippage models.
**Work Items**
- `app/models/signal_model.py` (XGBoost classifier + regression head)
- `app/models/regime_model.py` (GB/HMM)
- `notebooks/backtests.ipynb` or `app/backtest/engine.py` (transaction costs, slippage, extended-hours handling)
- Metrics: expectancy, drawdown, win rate, Sharpe; per-session splits
**Exit Criteria**
- Reproducible backtest report on ~12–24 months; CSV + charts produced.

---

## Milestone 4 — agent, risk & execution (paper trading) (Sprint 4, ~5–6 days)
**Goals**
- Close the loop: policy → risk gates → Alpaca paper execution with bracket orders.
**Work Items**
- `app/agent/policy.py` (entries/exits, session-aware throttles)
- `app/agent/sizing.py` (ATR/vol scaled; Kelly-lite; 50% AV manual gate)
- `app/agent/risk.py` (1%/trade, 5% DD halt, PDT guard, spread/slippage caps)
- `app/execution/alpaca_client.py` (limit+bracket in PRE/AFT; marketable limit in REG)
- DB persistence to **Azure Postgres**: `trades`, `orders`, `journal` (see `DATA_SCHEMA.md`)
**Exit Criteria**
- Paper orders placed; brackets attached; session + risk metadata stored in Postgres.

---

## Milestone 5 — dashboard & ops (Sprint 5, ~4–5 days)
**Goals**
- Visibility and controls for daily operations.
**Work Items**
- `app/monitoring/dashboard.py` (Streamlit): Today, Performance, Sessions, Watchlist, Diagnostics, Journal
- Export Prometheus metrics (optional) for Azure Monitor
- Log routing: App Service Log Stream + optional Log Analytics
**Exit Criteria**
- Dashboard live; per-session PnL/hit-rate/slippage charts; watchlist visible.

---

## Milestone 6 — CI/CD, secrets, and scheduling (Sprint 6, ~2–3 days)
**Goals**
- One-click deploy and time-based automation on Azure.
**Work Items**
- GitHub Actions: lint/test/build → deploy to **Azure App Service** (Linux container)
- Webhook endpoints for scheduled tasks (04:00 pre-scan, 06:15 finalize, 09:35/11:30/13:30 refresh, 16:05 AFT scan, 17:30 retrain)
- **Key Vault** integration via Managed Identity; Postgres VNet/private endpoint (as available)
**Exit Criteria**
- Successful deployment from `main`; cron jobs hitting app webhooks; secrets resolved at runtime.

---

## Milestone 7 — continuous learning & meta-agent (Sprint 7, ~4–5 days)
**Goals**
- Nightly retrain with drift detection; AI journaling and weekly retros.
**Work Items**
- `app/models/trainer.py` (rolling/expanding window; PSI/KL drift checks; model registry)
- MLflow/W&B integration (artifacts → Blob)
- `app/agent/meta_agent.py` (LangChain) to summarize performance and suggest parameter changes; open PRs for review
**Exit Criteria**
- Automated nightly retrain; weekly AI retrospective note with actionable recommendations.

---

## Milestone 8 — hardening & go/no-go (Sprint 8, ~3–4 days)
**Goals**
- Reliability tests, guardrail drills, and paper-trade SLA verification.
**Work Items**
- Chaos tests (data gaps, API failures, rate limits)
- Kill-switch drills; halts on 5% DD and infra anomalies
- Backtest ↔ paper decision parity ≥ 95%
**Exit Criteria**
- 4-week paper-trade report: expectancy > 0, drawdown < 15%, ≥ 2/4 weeks >= $50 PnL.

---

## Post-MVP Backlog
- Shorting small caps with borrow/SSR checks; halt-aware sizing cool-off
- News/NLP features (earnings PR, sentiment) with guardrails
- Options module (once equity edge proven); covered calls/put-selling
- Multi-venue data redundancy (Polygon fallback)
- Telegram/Discord notifier & manual-approval UI for 50% AV gate

---

## Risks & Mitigations
- **Extended-hours liquidity risk** → strict spread/slippage caps; limit+bracket only
- **PDT constraints on small account** → throttle intraday churn; favor swing holds
- **Data outages / API throttling** → Blob cache + exponential backoff; fail-closed
- **Model drift** → nightly retrain + drift detection; auto-rollback to last-stable

---

## Definitions of Done (DoD)
- Unit tests for all critical modules (data integrity, sizing math, risk halts)
- Session tags present on all market events and trades
- No secrets in repo; deployment via Actions to App Service is reproducible
- Dashboard shows per-session KPIs and watchlist on any trading day
