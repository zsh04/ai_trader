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
- `GET /watchlists` – List the latest snapshot per bucket (name, tags, symbol list, counts). Used by the Streamlit Watchlists page.
- `POST /watchlists` – Save symbols/tags to a bucket. Body: `{ "bucket": "core", "symbols": [...], "tags": ["daily"], "source": "streamlit-ui" }`.
- `POST /watchlists/{bucket}` – Same as above but with bucket in the path (legacy).
- `GET /watchlists/{bucket}/latest` – Raw snapshot for the named bucket.
- Legacy tasks endpoint `/tasks/watchlist` still exists for automation but the UI should call `/watchlists`.

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
