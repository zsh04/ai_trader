# Watchlist Specification

**Generation:**
- 04:00 PRE scan → rough list
- 06:15 PRE finalize → Opening Watchlist
- 09:35, 11:30, 13:30, 16:05 refreshes

**Filters:** price $1–$10, gap% ≥ 5, RVOL ≥ 3, premarket $ volume ≥ $1M, spread ≤ 0.75%, optional float ≤ 100M, optional news flag.

**Ranking:** dollar volume ↓, gap%, momentum strength, spread quality.

**Outputs:** `data/watchlists/YYYY-MM-DD.json` with fields: symbol, price, gap_pct, rvol, spread_pct, dollar_vol, float_est, session_eligibility.

## Data Sources
- **"finviz"** — Pulls symbols via `app.source.finviz_source.get_symbols`, applying the Finviz preset defined by `FINVIZ_WATCHLIST_PRESET`. Ideal for live scanner feeds.
- **"textlist"** — Parses a curated list from `WATCHLIST_TEXTLIST`, `WATCHLIST_TEXT`, or `WATCHLIST_TEXTLIST_FILE` using `app.source.textlist_source.get_symbols`. Intended for manual overrides or fallback lists.

## Request Parameters
- `source` (optional): `"finviz"` or `"textlist"`; defaults to environment variable `WATCHLIST_SOURCE`, falling back to `"textlist"`.
- `scanner` (optional): Named preset or strategy indicator (e.g., `"auto"`, `"breakout"`). Used by downstream builders where implemented.
- `limit` (optional): Integer cap on the number of symbols returned. Defaults to 15, maximum 100.
- `sort` (optional): Sort key for ordered outputs (e.g., `"momentum"`, `"gap_pct"`).

## Auto-Fallback Logic
1. Attempt to resolve the requested `source`.
2. If `"finviz"` fails (missing module, import error, or empty result), log a warning and retry with `"textlist"`.
3. If `"scanner"` is requested but not implemented, emit a single warning and fall back to `"textlist"`.
4. Unknown values default to `"textlist"` with a warning.

## Response Schema
All consumers (API route `/tasks/watchlist`, Telegram `/watchlist`, backend services) receive a normalized payload:

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

## Telegram Command Syntax
- `/watchlist` — Fetches the current symbols via the resolver (uses auto-fallback).
- `/watchlist auto 30` — Invokes the scanner-aware builder with `scanner="auto"` and `limit=30`.
- `/watchlist finviz --limit=20` — Overrides the source to Finviz, limiting output to 20 symbols.
- `/watchlist textlist AAPL TSLA` — Uses manual symbols while preserving normalization.

## Example Integration Test Response

```json
{
  "source": "textlist",
  "count": 2,
  "symbols": ["AAPL", "MSFT"]
}
```

This mirrors the expected output from `tests/unit/test_watchlist_route.py`, validating normalization and deduplication when `WATCHLIST_SOURCE=textlist`.
