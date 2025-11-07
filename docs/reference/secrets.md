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

## Usage guidelines

1. Reference secrets in App Service using `@Microsoft.KeyVault(SecretUri=https://...)` syntax.
2. Local development loads `.env` via python-dotenv; set fake tokens if not hitting real vendors.
3. Rotate broker + vendor keys quarterly; document rotation in `research-docs/project_notes.md`.

## See also

- [Managed Identity How-to](../howto/operations/managed-identity.md)
- [Configuration Defaults](./config.md)
- [CI/CD guide](../howto/operations/ci-cd.md)
