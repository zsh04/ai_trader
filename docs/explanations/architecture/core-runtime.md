---
title: Phase 1 — core runtime
summary: Explains how the DAL turns vendor data into probabilistic signals for live trading.
status: current
last_updated: 2025-11-11
type: explanation
---

# Phase 1 — core runtime

## Context

Phase 1 explains how we turn raw market data into the probabilistic signals used everywhere else. The priority is determinism: if a backtest uses a dataset, production should be able to replay the same bars + probabilistic frames.

## Runtime flow

1. **Symbol Universe**
   - `app/domain/watchlist_service.py` builds watchlists using DAL-backed vendors (`auto`, `alpha`, `finnhub`, `textlist`, `twelvedata`) and exposes `/tasks/watchlist` plus the Streamlit “Watchlist” pane.
   - The fallback sequence is Alpha Vantage → Finnhub → Textlist → Twelve Data so that the feature layer always has a non-empty symbol set.

2. **Market Data DAL**
   - `MarketDataDAL.fetch_bars()` normalises vendor payloads into canonical `Bars` objects (UTC timestamps, OHLCV, volume, source metadata).
   - `SignalFilteringAgent` runs Kalman/EMA/Butterworth filters to produce `SignalFrame` snapshots; `RegimeAnalysisAgent` tags each point with probabilistic regimes.
   - Results are cached to Parquet (`artifacts/marketdata/cache/…`) and optionally indexed in PostgreSQL for reproducibility.

3. **Strategy & Orchestration**
   - Strategies consume the DAL output directly. Breakout, momentum, and mean-reversion now share the LangGraph router (`app/orchestration/router.py`) which joins probabilistic features, computes priors, applies Fractional Kelly sizing, and publishes AEH order intents (or Alpaca paper orders when enabled).
   - A lightweight multi-timeframe aggregator remains available (`app/features/mtf_aggregate.py`) for scenarios that require raw OHLCV alignment instead of filtered series.

4. **Risk & Execution Interfaces**
   - Risk gates and execution adapters are defined (`app/agent/risk.py`, `app/execution/alpaca_client.py`) but guarded behind the Phase 4 milestone until the RiskManagementAgent is finalised.

```text
watchlist → MarketDataDAL → SignalFilteringAgent → Strategy → (future) Risk → Execution
```

## Responsibilities and rationale

- Maintain deterministic data ingestion regardless of vendor throttling by leveraging DAL fallbacks and cached parquet snapshots.
- Provide strategies with consistent features (filtered price, velocity, uncertainty, regimes) that are agnostic of the underlying vendor.
- Keep execution adapters isolated so orders can be introduced once risk controls (Phase 4) are ready.

## Open items

- Replace stub priors with ACA services (`svc-priors`, `svc-nlp`) and feed their outputs into the LangGraph router.
- Expand LangGraph regression tests (DAL ingest failures, risk/kill-switch paths) and surface metrics in the observability pipeline.
- Continue hardening watchlist ingestion once Marketstack/Tiingo vendors land.
