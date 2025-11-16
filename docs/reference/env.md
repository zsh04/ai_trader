---
title: Environment Variables
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-15
toc: true
---

# Environment Variables

This page summarizes the required and optional configuration knobs for each service in AI Trader. Use it as a checklist whenever you provision a new environment (dev, paper, prod). Unless noted otherwise, values live in Azure App Service application settings, surfaced via Key Vault references and Managed Identity.

## API (ai-trader-api)

| Variable | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | ✅ | PostgreSQL Flexible Server connection string. Use the SSL-enabled URI (`postgresql://user:pass@host:port/db?sslmode=require`). |
| `ALPACA_API_KEY`, `ALPACA_API_SECRET` | 🔐 (paper/live) | Alpaca broker credentials. Optional in dev, required when router/order consumer runs. |
| `ALPACA_DATA_FEED` | optional | `iex` (default) or `sip`. Controls Alpaca market data endpoint. |
| `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_CONTAINER` | ✅ | Blob account + container for probabilistic frames and adapters. Usually satisfied via Managed Identity (`AzureWebJobsStorage` style). |
| `CHECKPOINT_CONTAINER`, `EH_FQDN`, `EH_HUB_*`, `EH_CONSUMER_GROUP` | optional | Event Hub names for DAL smoke/events/order consumer. Set when Event Hub ingestion is enabled. |
| `WATCHLIST_SOURCE`, `TEXTLIST_BACKENDS` | optional | Default source for watchlists (`auto`, `alpha`, `finnhub`, `textlist`). |
| `ALPHAVANTAGE_API_KEY`, `FINNHUB_API_KEY`, `TWELVEDATA_API_KEY` | optional | Vendor keys consumed by the DAL fallback chain. Missing keys trigger fallbacks; provide them in prod to avoid degraded watchlists. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | ✅ | Collector endpoint (e.g., `https://ai-trader-otel...:4318/v1/traces`). UI + API share the same collector. |
| `OTEL_RESOURCE_ATTRIBUTES` | optional | `deployment.environment=prod,service.version=1.6.6` etc. |
| `SENTRY_DSN` | optional | DSN if Sentry is enabled. |
| `APP_VERSION` | optional | Injected at build-time; used for `/version` and metrics. |

## UI (ai-trader-ui)

| Variable | Required | Description |
| --- | --- | --- |
| `API_BASE_URL` | ✅ | Control-plane API hostname (e.g., Front Door FQDN). All Streamlit actions call this host. |
| `SERVICE_NAME` | optional | Defaults to `ai-trader-ui`; used in telemetry. |
| `ENV` | optional | Text label for the deployment (`dev`, `int`, `prod`). |
| `FEATURE_CHRONOS2`, `FEATURE_BACKTEST_SWEEPS`, `FEATURE_DEMO_DATA` | optional | Boolean flags (string values `true/false`). Gate UI sections. |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_EXPORTER_OTLP_HEADERS` | ✅ | Same collector endpoint as the API, plus optional headers (for auth). |
| `FARO_URL`, `FARO_APP_ID`, `FARO_APP_NAME` | optional | Grafana Faro configuration for RUM. Set when client telemetry is required. |
| `HTTP_RETRIES`, `HTTP_BACKOFF` | optional | Overrides for the shared HTTP client (useful when testing). |

## Order Consumer / Workers

| Variable | Required | Description |
| --- | --- | --- |
| `EH_FQDN`, `EH_HUB_ORDERS`, `EH_CONSUMER_GROUP` | ✅ | Identifiers for the `exec.orders` Event Hub feed. |
| `STORAGE_ACCOUNT`, `CHECKPOINT_CONTAINER` | optional | Blob container for checkpointing. Defaults to MI-based access. |
| `DATABASE_URL` | ✅ | Same Postgres connection string used by the API (read/write for orders/fills). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | optional | Collector endpoint for worker spans. |

## svc-nlp (FinBERT) & svc-forecast (Chronos-2)

These Container Apps share the same knobs:

| Variable | Required | Description |
| --- | --- | --- |
| `MODEL_ID_FINBERT` / `MODEL_ID_CHRONOS2` | ✅ | Hugging Face repo IDs (`ProsusAI/finbert`, `amazon/chronos-2`). |
| `HF_COMMIT_SHA` | ✅ | Specific model commit SHA for reproducibility. |
| `ADAPTER_TAG` | optional | Default baked-in adapter tag (e.g., `base`). |
| `BLOB_MODELS_URL`, `BLOB_ADAPTERS_URL`, `STORAGE_ACCOUNT` | ✅ | Blob URLs the runtime uses to fetch adapters (`blob://models/...`, `blob://adapters/...`). Set up MI with `Storage Blob Data Reader`. |
| `MODEL_CACHE_DIR` | optional | Path for `/models-cache`. Defaults to `/models-cache`. |
| `ALLOW_HF` | optional | Set to `1` to allow direct HF downloads (dev only). |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS` | optional | Telemetry collector configuration. |
| `APP_ENVIRONMENT`, `APP_VERSION` | optional | Metadata for logs/spans. |

## svc-priors (future)

When the priors service is enabled, it will mirror the svc-nlp settings with additional vendor/API keys as required.

## Shared secrets / Key Vault

The following keys are stored in Key Vault and referenced by App Service:

- `postgres-connection-string`
- `alpaca-api-key`, `alpaca-api-secret`
- `alphavantage-api-key`, `finnhub-api-key`, `twelvedata-api-key`
- `grafana-faro-url`, `grafana-faro-app-id`

Grant the relevant managed identities (`ai-trader-api-mi`, `ai-trader-ui-mi`, worker identities) `Key Vault Secrets User` access to read them.

## Checklist

1. **API**: Verify DB URL, Alpaca keys, storage account, EH settings, and vendor keys set and linked via MI.
2. **UI**: Set `API_BASE_URL`, feature flags, OTEL/Faro envs.
3. **Workers**: Ensure Event Hub + Postgres envs and MI assignments match.
4. **Model services**: Confirm blob URLs and adapter tags exist, MI has `Storage Blob Data Reader`.
5. **Telemetry**: Point every service’s `OTEL_EXPORTER_OTLP_ENDPOINT` to the same collector, including `/v1/traces`.

### Verifying Azure Blob configuration

Run `python scripts/check_blob_env.py` from the repo root (or invoke it in the container/VM via `./scripts/check_blob_env.py`). The helper inspects the following in priority order:

1. `AZURE_STORAGE_CONNECTION_STRING`
2. `AZURE_STORAGE_ACCOUNT` + `AZURE_STORAGE_ACCOUNT_KEY`
3. `AZURE_STORAGE_CONTAINER_NAME` / `AZURE_STORAGE_CONTAINER_DATA`

If the connection string is absent, the script enforces the account/key/container trio and exits with a non-zero code when any value is missing. Wire this into your build/test pipelines to catch misconfigured environments before the backtest artifacts attempt to upload.
