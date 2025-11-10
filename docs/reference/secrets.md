---
title: "Secrets & Key Vault"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-06
toc: true
---

# Secrets & Key Vault

## Purpose

Authoritative mapping between Azure Key Vault secrets, App Service settings, and their usage across the stack. All production secrets flow through Managed Identity references; `.env` holds only local placeholders.

## Secret matrix

| Key Vault secret | App Setting / env | Purpose |
|------------------|-------------------|---------|
| `ALPACA-KEY-ID` | `ALPACA_API_KEY` | Broker API key (paper/live) |
| `ALPACA-SECRET-KEY` | `ALPACA_API_SECRET` | Broker secret |
| `ALPHAVANTAGE-API-KEY` | `ALPHAVANTAGE_API_KEY` | Intraday + EOD market data |
| `FINNHUB-API-KEY` | `FINNHUB_API_KEY` | Daily quote fallback |
| `TWELVEDATA-API-KEY` | `TWELVEDATA_API_KEY` | Symbol lists + watchlist fallback |
| `YAHOO-REFRESH-TOKEN` | `YAHOO_API_TOKEN` | Vendor auth when needed |
| `POSTGRES-CONN` | `DATABASE_URL` | SQLAlchemy connection string |
| `BLOB-CONN` | `AZURE_STORAGE_CONNECTION_STRING` | Artifacts + model cache |
| `TELEMETRY-CONN` | `APPINSIGHTS_CONNECTION_STRING` | OTEL exporter |

## CI / Managed identity mapping

| Identity | Scope | Key Vault / resource access | Notes |
|----------|-------|-----------------------------|-------|
| `ai-trader-api-mi` (OID ending `…85df`) | API App Service | Key Vault (read secrets), Event Hubs Data Sender/Receiver, Storage Blob Data Contributor (`aitraderblobstore`) | Used by runtime + DAL smoke endpoint to publish telemetry. |
| `ai-trader-ui-mi` (OID ending `…4bb7`) | Streamlit UI App Service | Same as above | Enables UI to read secrets + send Event Hub events. |
| `gh-ai-trader-ci` (GitHub Actions) | CI pipelines (terraform/CLI) | Key Vault get/list + Storage (artifact uploads) via federated credential | Update when adding new pipelines; keep scope minimal. |

When onboarding a new service or pipeline, grant the minimal role (`Key Vault Secrets User`, `Azure Event Hubs Data Sender`, etc.) and document it here.

## Usage guidelines

1. Reference secrets in App Service using `@Microsoft.KeyVault(SecretUri=https://...)` syntax.
2. Local development loads `.env` via python-dotenv; set fake tokens if not hitting real vendors.
3. Rotate broker + vendor keys quarterly; document rotation in `research-docs/project_notes.md`.

## See also

- [Managed Identity How-to](../howto/operations/managed-identity.md)
- [Configuration Defaults](./config.md)
- [CI/CD guide](../howto/operations/ci-cd.md)
