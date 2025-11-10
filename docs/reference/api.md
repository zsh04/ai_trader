---
title: "API Reference"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-06
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
- `POST /backtests/run` – Run single backtest (`symbol`, `start`, `strategy`, `params`). Returns metrics + equity paths.
- `POST /backtests/sweeps` – Kick off parameter sweep (YAML config path or inline grid). Returns job ID; results streamed via Event Hubs + `/backtests/sweeps/{job_id}`.
- `GET /backtests/sweeps/{job_id}` – Inspect sweep status/results.

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
