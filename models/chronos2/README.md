# ai-trader-forecast (Chronos-2)

Forecasting microservice exposing a deterministic interface that will host the Chronos-2 foundation model.

## Runtime overview

- Base model metadata: `amazon/chronos-2` (`MODEL_ID_CHRONOS2`).
- Hybrid adapters identical to FinBERT flow (`adapters/chronos2/<tag>/adapter.tar.gz`). Adaptations are unpacked into `/models-cache/chronos2` and recorded in `effective.json`.
- Current CPU build ships with a lightweight trend forecaster so the ACA surface is live while Chronos integration is hardened. The adapter plumbing, OTEL metadata, and Blob contract match what Chronos will require, so swapping the inference core only touches `runtime.py`.

## Environment variables

| Name | Required | Description |
|------|----------|-------------|
| `MODEL_ID_CHRONOS2` | optional | HF repo id (default `amazon/chronos-2`). |
| `HF_COMMIT_SHA` | optional | Commit pin for deterministic caching. |
| `BAKED_ADAPTER_TAG` | optional | Adapter baked into the image (default `base`). |
| `ADAPTER_TAG` | optional | Runtime override adapter tag. |
| `STORAGE_ACCOUNT` / `STG_ACCOUNT` | when adapters needed | Azure Storage account name. |
| `BLOB_ADAPTERS_URL` | optional | `blob://adapters` by default; support `blob://adapters/chronos2`. |
| `MODEL_CACHE_DIR` | optional | Cache path (default `/models-cache`). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_HEADERS` | optional | OTEL collector configuration. |

## Build notes

This image also targets `python:3.12-slim`. If torch/transformers wheels are unavailable, fall back to `python:3.11-slim` and record the exception in `docs/ops/model-artifacts.md`.

## Local run

```bash
uvicorn app.server:app --port 8001
```

Test:
```bash
curl -X POST localhost:8001/forecast \
  -H 'Content-Type: application/json' \
  -d '{"series": [100, 101, 103], "horizon": 3}'
```
