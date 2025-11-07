---
title: Data abstraction layer (DAL)
summary: Explains the goals, vendor coverage, and reliability mechanisms of the probabilistic data layer.
status: current
last_updated: 2025-11-06
type: explanation
---

# Data abstraction layer (DAL)

## Problem & goals

Backtests and production code must see identical bars and probabilistic features even when we rotate vendors. The DAL normalises vendor payloads into canonical `Bars` + `SignalFrame` models and applies Kalman-based filtering/regime classification so downstream strategies remain vendor-agnostic.

Goals:

- **Source agnostic:** callers never read vendor-specific responses.
- **Extensible:** new vendors should require only a `VendorClient` implementation.
- **Deterministic:** cached parquet + Postgres metadata guarantee we can replay any fetch/stream.

## Current vendors

| Vendor | Transport | Notes |
|--------|-----------|-------|
| Alpaca | HTTP + WebSocket | Primary intraday source; supports streaming and HTTP backfill. |
| Alpha Vantage | HTTP | Intraday + daily; daily automatically falls back to Yahoo/Twelve Data when rate-limited. |
| Yahoo/Twelve Data | HTTP | Used as Alpha Vantage fallback and for watchlist validation. |
| Finnhub | HTTP | Daily quote endpoint only (intraday gated behind higher plan). |

`MarketDataDAL.fetch_bars()` takes `symbol`, `start`, `end`, `interval`, `vendor`, and returns a `ProbabilisticBatch` (bars, `SignalFrame`s, regime snapshots, cache paths). `.stream_bars()` yields `ProbabilisticStreamFrame`s for streaming-aware vendors.

## Unified models

```text
Bar:
  symbol, vendor, timestamp (UTC), open, high, low, close, volume, timezone, source

SignalFrame:
  symbol, vendor, timestamp, price, filtered_price, velocity, uncertainty,
  butterworth_price?, ema_price?
```

All timestamps are timezone-aware and normalised to UTC for storage, with the vendor’s timezone preserved separately for context.

## Probabilistic pipeline

1. Vendor client fetches raw bars.
2. Normaliser produces `Bars` and ensures schema conformity.
3. `SignalFilteringAgent` applies Kalman, Butterworth, and EMA filters.
4. `RegimeAnalysisAgent` classifies each point (`trend_up`, `sideways`, etc.) with uncertainty values.
5. Outputs are cached to `artifacts/marketdata/cache/...` and optionally persisted via `MarketRepository` in PostgreSQL.

## Reliability features

- **Fallback chain:** Alpha Vantage → Yahoo → Twelve Data; `auto` watchlists follow Alpha Vantage → Finnhub → Textlist → Twelve Data.
- **Caching:** deterministic parquet filenames per vendor/symbol/interval so repeated runs reuse data.
- **Metadata:** Postgres entries store vendor, timezone, cache paths, and fetch parameters for auditing.

## References

- `app/dal/manager.py`, `app/dal/vendors/market_data/*`
- `app/agent/probabilistic/*` (signal + regime agents)
- `docs/reference/database.md` (schema tables that store DAL outputs)
