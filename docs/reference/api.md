---
title: "API Reference"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-14
toc: true
---

# API Reference

## Synopsis
API Gateway endpoints and contracts.

## Auth
Bearer tokens (JWT) or API keys; scopes and roles.

## OpenAPI
Link/path to `openapi.yaml`.

## Endpoints

### Operations / health
- `GET /health/live`, `GET /health/ready` – FastAPI probes.
- `POST /ops/dal-smoke` – Trigger DAL smoke test (Alpha Vantage + Finnhub); returns per-vendor status.
- `GET /ops/prob-frame` – Fetch cached probabilistic frame preview (symbol, strategy, vendor, interval).
- `POST /ops/eventhub-test` – Publish arbitrary payload to a configured Event Hub (diagnostic only).

### Backtests
- `POST /backtests/run` – Run single backtest. Body supports:
  - `symbol`, `start`, `end`, `strategy`, `params`.
  - Probabilistic controls: `use_probabilistic`, `dal_vendor`, `dal_interval`, `regime_aware_sizing`.
  - Risk knobs: `risk_agent`, `risk_agent_fraction`, `slippage_bps`, `fee_per_share`, `risk_frac`, `min_notional`.
  Response bundles metrics, equity CSV path, and `prob_frame_path` so Streamlit/UI can replay the persisted probabilistic frame without re-fetching vendors.
- `POST /backtests/sweeps` – Kick off parameter sweep (YAML config path or inline grid). Returns job ID; results streamed via Event Hubs + `/backtests/sweeps/{job_id}`.
- `GET /backtests/sweeps/{job_id}` – Inspect sweep status/results.
- `GET /backtests/sweeps/jobs` – List sweep job manifest entries (queued/running/completed) with duration/strategy metadata.
- `GET /backtests/sweeps/jobs/{job_id}` – Filter manifest entries for a specific job ID.
- `POST /backtests/sweeps/jobs` – Enqueue a sweep job by emitting an `EH_HUB_JOBS` message (consumed by the ACA job or orchestrator). Body accepts `config_path`, `strategy`, `symbol`, and optional metadata; response returns the queued job id/status.

### Router / orchestration
- `POST /router/run` – Execute the LangGraph router (ingest → priors → strategy → Fractional Kelly → enqueue). Body mirrors `RouterRequest` plus toggles `offline_mode`, `publish_orders`, `execute_orders`. Response includes run metadata, priors, and the generated `order_intent` (qty/notional/price hints). Requires Alpaca keys if `execute_orders=true`.

### Orders
- `GET /orders` – Returns the latest persisted orders (up to `limit`), populated by the Event Hubs consumer. Each record includes symbol, side, qty, status, `submitted_at`, strategy/run metadata, and `broker_order_id` if execution succeeded.

### Fills / trades
- `GET /fills` – Lists recent fills (optionally filtered by `symbol`). Provides `order_id`, qty, price, fees, and PnL so Streamlit or downstream tools can render realized trades without direct DB access.

### Watchlists
- A *bucket* is just a slug for the list you want to manage (`intraday-core`, `swing-tech`, etc.). Think of it as a saved view — anything that writes to that bucket replaces the latest snapshot that `/watchlists` will show. Symbols are expected to be upper-case strings; tags are free-form labels you can filter on in Streamlit.
- `GET /watchlists` – Latest snapshot per bucket with `name`, `asof_utc`, `source`, `count`, `symbols`, and `tags`.
- `POST /watchlists` – Save a snapshot. Example:
  ```json
  {
    "bucket": "intraday-core",
    "symbols": ["AAPL", "MSFT", "NVDA", "META"],
    "tags": ["intraday", "tier1"],
    "source": "streamlit-ui",
    "meta": { "owner": "ops", "notes": "pre-market scan" }
  }
  ```
- `POST /watchlists/{bucket}` – Path-param form of the same payload.
- `GET /watchlists/{bucket}/latest` / `{bucket}/{yyyymmdd}` – Retrieve an exact snapshot (useful for audits or recreating past scans).

### Portfolio / trading data
- `GET /positions` – Current net positions (symbol, qty, average price, realized/unrealized P&L, leverage metadata). Backed by the `trading.positions` table that the execution consumer maintains.
- `GET /equity/{account}?limit=390` – Equity curve for the requested account slug (we store a single book today; `account` is a label so Streamlit can show multiple tabs later). Returns `{ "account": "paper", "points": [{ "ts": "...", "equity": 200000.0, ...}] }`.
- `GET /trades/{symbol}` – Recent fills. Pass `all` or `*` to include every symbol, otherwise restricts to the ticker provided.

### Models
- `GET /models` – Return FinBERT + Chronos-2 deployment metadata (adapter tag, warm status, shadow toggle, last sync times).
- `POST /models/{service}/warm` – Trigger cache warm-up for the model microservice (paper/live).
- `POST /models/{service}/adapters/sync` – Force an adapter refresh from Blob Storage; optional body `{ "adapter_tag": "20251114-lora-a" }`.
- `POST /models/{service}/shadow` – Toggle the shadow traffic flag so operators can run canaries before routing production flow.

## Rate limits & retries
State limits; backoff guidance for 429.

## Error model
`{ code, message, details }` with stable codes.

## See also
- [Data Models](./data-models.md)
- [SRE & SLOs](./sre-slos.md)
- [Architecture overview](../explanations/architecture/overview.md)
