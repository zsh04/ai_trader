---
title: "API Reference"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-10
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

### Router / orchestration
- `POST /router/run` – Execute the LangGraph router (ingest → priors → strategy → Fractional Kelly → enqueue). Body mirrors `RouterRequest` plus toggles `offline_mode`, `publish_orders`, `execute_orders`. Response includes run metadata, priors, and the generated `order_intent` (qty/notional/price hints). Requires Alpaca keys if `execute_orders=true`.

### Watchlists
- `POST /tasks/watchlist` – Build watchlist (manual symbols or scanner).
- `GET /tasks/watchlist` / `GET /watchlist` – Retrieve current watchlist snapshot.

*(Order endpoints are deferred to Phase 3 once execution wiring lands.)*

## Rate limits & retries
State limits; backoff guidance for 429.

## Error model
`{ code, message, details }` with stable codes.

## See also
- [Data Models](./data-models.md)
- [SRE & SLOs](./sre-slos.md)
- [Architecture overview](../explanations/architecture/overview.md)
