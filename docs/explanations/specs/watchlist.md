---
title: Watchlist specification
summary: Describes how daily watchlists are generated, filtered, and served via the DAL-backed services.
status: current
last_updated: 2025-11-06
type: explanation
---

# Watchlist specification

## Context

Watchlists seed every downstream component (scanners, backtests, live strategies). The schedule mirrors the trader workflow: premarket rough list at 04:00, opening list at 06:15, and refreshes at 09:35/11:30/13:30/16:05.

## Filters and ranking

- Price between $1–$10.
- Gap ≥ 5 %, relative volume ≥ 3, premarket dollar volume ≥ $1 M.
- Spread ≤ 0.75 %; optional float cap (≤ 100 M) and news flag apply per scanner.
- Ranking prioritises dollar volume, gap strength, momentum, and spread quality.

Daily outputs land in `data/watchlists/YYYY-MM-DD.json` with `symbol`, `price`, `gap_pct`, `rvol`, `spread_pct`, `dollar_vol`, `float_est`, and `session_eligibility` fields.

## Data Sources
- **"alpha"** — Pulls symbols via Alpha Vantage (`watchlist_sources.fetch_alpha_vantage_symbols`).
- **"finnhub"** — Pulls symbols via Finnhub (`watchlist_sources.fetch_finnhub_symbols`); limited to listing endpoints under the current plan.
- **"twelvedata"** — Optional fallback using Twelve Data (`watchlist_sources.fetch_twelvedata_symbols`).
- **"textlist"** — Parses a curated list from `WATCHLIST_TEXTLIST`, `WATCHLIST_TEXT`, or `WATCHLIST_TEXTLIST_FILE` using `app.sources.textlist_source.get_symbols`. Intended for manual overrides or fallback lists.

## Request Parameters
- `source` (optional): `"alpha"`, `"finnhub"`, `"twelvedata"`, or `"textlist"`; defaults to environment variable `WATCHLIST_SOURCE`, falling back to `"textlist"`.
- `scanner` (optional): Named preset or strategy indicator (e.g., `"auto"`, `"breakout"`). Used by downstream builders where implemented.
- `limit` (optional): Integer cap on the number of symbols returned. Defaults to 15, maximum 100.
- `sort` (optional): Sort key for ordered outputs (e.g., `"momentum"`, `"gap_pct"`).


## Auto-fallback logic
1. Attempt to resolve the requested `source`.
2. `auto` maps to `"alpha"` first; if Alpha Vantage fails (missing key, rate limit, empty result), fall back to `"finnhub"`, then `"textlist"`, then `"twelvedata"`.
3. If `"scanner"` is requested but not implemented, emit a single warning and fall back to `"textlist"`.
4. Unknown values default to `"textlist"` with a warning.

## Response schema
All consumers (API route `/tasks/watchlist`, backend services) receive a normalized payload:

```json
{
  "source": "textlist",
  "count": 12,
  "symbols": ["AAPL", "MSFT", "NVDA", "..."]
}
```

- `source`: string identifier of the data source actually used after fallback.
- `count`: integer number of unique symbols returned.
- `symbols`: array of uppercase ticker strings in stable insertion order.

## Example integration test response

```json
{
  "source": "textlist",
  "count": 2,
  "symbols": ["AAPL", "MSFT"]
}
```

This mirrors the expected output from `tests/unit/test_watchlist_route.py`, validating normalization and deduplication when `WATCHLIST_SOURCE=textlist`.
