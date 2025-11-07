---
title: "Market Data Sources"
doc_type: reference
audience: intermediate
product_area: data
last_verified: 2025-11-06
toc: true
---

# Market Data Sources

## Purpose

Document available vendor adapters under `app/dal/vendors/market_data` and how they fail over.

## Vendors

| Alias | Transport | Coverage | Notes |
|-------|-----------|----------|-------|
| `alpaca_ws` / `alpaca_http` | WebSocket + REST | Intraday bars, streaming | Primary source for live trading |
| `alphavantage_http` | REST | 1,5,15,30,60-min intraday + EOD | MCP optional, fallback to Yahoo/Twelve Data on rate limits |
| `finnhub_http` | REST | Daily quote snapshot | Intraday disabled until plan upgrade |
| `yahoo_http` | REST | Daily/EOD fallback | Used when Alpha Vantage throttles |
| `twelvedata_http` | REST | Symbol discovery, quote fallback | Also seeds watchlist metadata |

## Failover chain

1. Attempt streaming (Alpaca WS). On reconnect, backfill via Alpaca HTTP.
2. For EOD bars, call Alpha Vantage; if missing interval or throttled, fallback to Yahoo then Twelve Data.
3. Finnhub currently serves only `/quote` for sanity checks; treat 403s as soft failures.

## Storage targets

- All vendors emit normalized `SignalFrame` objects saved to Parquet (`artifacts/dal/`).
- Metadata registered in PostgreSQL `market.symbols`.

## See also

- [Market Data Schemas](./data-schema.md)
- [DAL explanation](../explanations/architecture/core-runtime.md)
- [How-to: DAL smoke test](../howto/runbooks.md) *(if applicable)*
