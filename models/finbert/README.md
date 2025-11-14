# ai-trader-nlp (FinBERT)

FastAPI microservice exposing FinBERT sentiment classification with hybrid adapter support.

## Runtime overview

- Base model: `ProsusAI/finbert` (HF commit passed through `HF_COMMIT_SHA`).
- Hybrid adapters: baked tag declared at build time, optional runtime tag via `ADAPTER_TAG`. If runtime tag differs, service fetches `adapters/finbert/<tag>/adapter.tar.gz` from `aitraderblobstore` using managed identity and PEFT-merges the weights.
- Cache: `/models-cache/finbert` stores downloaded adapters and `effective.json` (hf_sha, adapter_tag, loaded_at).
- OTEL: resource attributes include `ai.model.id`, `ai.hf.repo.sha`, `ai.adapter.tag`, `service.instance.id`.

## Environment variables

| Name | Required | Description |
|------|----------|-------------|
| `MODEL_ID_FINBERT` | optional | HF repo id (default `ProsusAI/finbert`). |
| `HF_COMMIT_SHA` | optional | Pin to a commit SHA for deterministic builds. |
| `BAKED_ADAPTER_TAG` | optional | Tag compiled into the image (default `base`). |
| `ADAPTER_TAG` | optional | Runtime override. |
| `STORAGE_ACCOUNT` / `STG_ACCOUNT` | when adapters needed | Azure Storage account hosting `models/` + `adapters/`. |
| `BLOB_ADAPTERS_URL` | optional | `blob://<container>[/prefix]` describing adapter container (default `blob://adapters`). |
| `MODEL_CACHE_DIR` | optional | Override cache path (default `/models-cache`). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | optional | OTEL collector endpoint. |
| `OTEL_EXPORTER_OTLP_HEADERS` | optional | Collector headers (usually provided via ACA secret). |

## Build notes

Images default to `python:3.12-slim`. If PyTorch/Transformers wheels are unavailable for the target architecture, switch the base image to `python:3.11-slim` **for this service only** and record the rationale in `docs/ops/model-artifacts.md`.

## Local run

```bash
export MODEL_ID_FINBERT=ProsusAI/finbert
export HF_COMMIT_SHA=main
export ADAPTER_TAG=base
uvicorn app.server:app --reload --port 8000
```

POST `http://localhost:8000/classify-sentiment` with `{ "text": "Stocks rally on upbeat earnings" }` to receive `{ label, score, adapter_tag, hf_sha }`.
