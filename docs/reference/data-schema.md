---
title: "Market Data Schemas"
doc_type: reference
audience: intermediate
product_area: data
last_verified: 2025-11-06
toc: true
---

# Market Data Schemas

## Purpose

Canonical columns and types for bars, quotes, and probabilistic annotations emitted by MarketDataDAL vendors. All downstream tooling (DAL snapshots, parquet exports, backtests) should emit/consume these schemas.

## Candle schema

| Column | Type | Notes |
|--------|------|-------|
| `ts` | `int64` (epoch ms) | Time is always timezone-aware UTC |
| `open`, `high`, `low`, `close` | `float64` | Adjusted for corporate actions |
| `volume` | `int64` | Raw exchange volume |
| `vwap` | `float64` | Optional vendor field |
| `source` | `string` | Vendor alias (alpaca_ws, alphavantage_http, yahoo_http, etc.) |

## Probabilistic annotations

| Column | Type | Description |
|--------|------|-------------|
| `price_filtered` | `float64` | Kalman-filtered price |
| `velocity` | `float64` | First derivative from Kalman state |
| `uncertainty_p` | `float64` | Covariance estimate |
| `ema_fast`, `ema_slow` | `float64` | Optional EMA overlays |
| `butterworth` | `float64` | Optional Butterworth smoothed price |

## Signal frame contract

```
SignalFrame = {
  "symbol": str,
  "bars": List[Candle],
  "prob": Dict[str, float],
  "regime": Optional[str],
  "meta": Dict[str, Any]
}
```

## Storage layout

- Parquet partitions: `vendor=alpaca_ws/date=YYYY-MM-DD/symbol=AAPL/part-*.snappy.parquet`
- Metadata index (PostgreSQL): `signals (symbol, ts, vendor, regime, hash)`.

## See also

- [Data Models](./data-models.md)
- [Sources Reference](./sources.md)
- [Backtesting architecture explanation](../explanations/architecture/backtesting.md)
