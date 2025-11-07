---
title: Phase 1 — core runtime
summary: Explains how the DAL turns vendor data into probabilistic signals for live trading.
status: current
last_updated: 2025-11-06
type: explanation
---

# Phase 1 — core runtime

## Context

Phase 1 explains how we turn raw market data into the probabilistic signals used everywhere else. The priority is determinism: if a backtest uses a dataset, production should be able to replay the same bars + probabilistic frames.

## Runtime flow

1. **Symbol Universe**
   - `app/services/watchlist_service.py` builds watchlists using DAL-backed vendors (`auto`, `alpha`, `finnhub`, `textlist`, `twelvedata`).
   - The fallback sequence is Alpha Vantage → Finnhub → Textlist → Twelve Data so that the feature layer always has a non-empty symbol set.

2. **Market Data DAL**
   - `MarketDataDAL.fetch_bars()` normalises vendor payloads into canonical `Bars` objects (UTC timestamps, OHLCV, volume, source metadata).
   - `SignalFilteringAgent` runs Kalman/EMA/Butterworth filters to produce `SignalFrame` snapshots; `RegimeAnalysisAgent` tags each point with probabilistic regimes.
   - Results are cached to Parquet (`artifacts/marketdata/cache/…`) and optionally indexed in PostgreSQL for reproducibility.

3. **Strategy Input**
   - Strategies consume the DAL output directly. Breakout signalling is operational; momentum/mean-reversion consumers will reuse the same probabilistic features once complete.
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

- Wire momentum/mean-reversion strategies to the probabilistic feature set (Phase 3 dependency).
- Finalise `RiskManagementAgent` to translate strategy signals into executable orders.
- Expand test coverage so watchdog alerts flag when DAL fallbacks are triggered or parquet caches grow stale.
