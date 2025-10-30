# Market Data Sources — Comparative Research

## Purpose

Evaluate additional data sources to improve watchlist enrichment, scanner coverage, backtest fidelity, and AI context.

## Candidates (Initial)

- Finviz (screeners, TA, fundamentals; HTML/unofficial API)
- TradingView (charts, indicators, websockets)
- Polygon.io (full-market US equities/crypto/forex)
- IEX Cloud (US equities)
- Tiingo (EOD + news)
- Nasdaq Data Link (Quandl)
- Marketstack (lightweight OHLC/fundamentals)
- NewsAPI / Finnhub (news + sentiment)
- Reddit/Twitter/X (retail chatter)

## Evaluation Matrix

| Source          | Data Types            | Latency  | Historical Depth | Rate Limits | Auth/Pricing   | Integration Effort | Notes               |
| --------------- | --------------------- | -------- | ---------------- | ----------- | -------------- | ------------------ | ------------------- |
| Finviz          | Screener/TA           | Daily    | N/A              | Page scrape | None           | Med                | Good daily screener |
| TradingView     | Realtime + indicators | Low      | Good             | Websocket   | N/A            | High               | Complex protocol    |
| Polygon.io      | Realtime/Historic     | Low      | Deep             | Tiered      | API Key (paid) | Med                | Solid US data       |
| IEX Cloud       | EOD/Realtime          | Low      | Good             | Tiered      | API Key        | Low                | Good starter        |
| Tiingo          | EOD + news            | Med      | Good             | Tiered      | API Key        | Low                | Inexpensive         |
| Nasdaq DL       | Macro/alt             | Varies   | Varies           | Tiered      | API Key        | Low                | Reference datasets  |
| Marketstack     | EOD+                  | Med      | OK               | Tiered      | API Key        | Low                | Simple fallback     |
| NewsAPI/Finnhub | News/Signal           | Med      | N/A              | Tiered      | API Key        | Low                | AI signals          |
| Reddit/Twitter  | Social                | Realtime | N/A              | API limits  | OAuth          | Med                | Noisy but useful    |

## Suitability by Use Case

- **Watchlist enrichment:** Finviz, Polygon, IEX, Tiingo
- **Scanners/screeners:** Finviz, TradingView, Polygon
- **Backtest fidelity:** Polygon, Tiingo (EOD), IEX (with caveats)
- **AI context (news/sentiment):** NewsAPI, Finnhub, social APIs

## Sample API (to capture)

- Auth model, sample curl + JSON schema, typical rate limits, error semantics.

## Recommendation (draft)

- Phase 1: Finviz (screener), Polygon (data), Tiingo (EOD/news)
- Phase 2: TradingView (realtime/indicators), NewsAPI/Finnhub (sentiment)

## Next Steps

- POC: Build adapters under `app/sources/` with unified `get_symbols()` / `fetch_ohlcv()` signatures.
- Add integration tests and CI env guards.
