# Secrets & Key Vault Conventions

All sensitive configuration values are stored in Azure Key Vault and injected
into the application via App Service settings (API + UI) or GitHub Actions
secrets. Use the following mapping as the canonical source of truth whenever new
secrets are provisioned or rotated:

| Key Vault secret name              | App Setting env var              | Purpose                                |
|------------------------------------|----------------------------------|----------------------------------------|
| `ALPACA-KEY-ID`                    | `ALPACA_API_KEY`                 | Alpaca broker API key (paper/live)     |
| `ALPACA-SECRET-KEY`                | `ALPACA_API_SECRET`              | Alpaca broker API secret               |
| `ALPHAVANTAGE-API-KEY`             | `ALPHAVANTAGE_API_KEY`           | Alpha Vantage intraday/EOD key *(falls back to Yahoo/TwelveData when rate-limited)* |
| `FINNHUB-API-KEY`                  | `FINNHUB_API_KEY`                | Finnhub daily quote key *(intraday disabled until paid plan)* |
| `TWELVEDATA-API-KEY` *(optional)*  | `TWELVEDATA_API_KEY`             | Twelve Data fallback feed              |
| `AZURE-STORAGE-CONNECTION-STRING`  | `AZURE_STORAGE_CONNECTION_STRING`| Full Blob storage connection (legacy)  |
| `AZURE-STORAGE-ACCOUNT-KEY`        | `AZURE_STORAGE_ACCOUNT_KEY`      | Storage account key (legacy)           |
| `DATABASE-URL`                     | `DATABASE_URL`                   | Primary Postgres DSN (Flexible Server) |
| `PG-PASSWORD`                      | `PGPASSWORD`                     | Postgres password for manual clients   |
| `TELEGRAM-BOT-TOKEN`               | `TELEGRAM_BOT_TOKEN`             | Telegram bot credential                |
| `TELEGRAM-WEBHOOK-SECRET`          | `TELEGRAM_WEBHOOK_SECRET`        | Telegram webhook shared secret         |
| `TELEGRAM-DEFAULT-CHAT-ID`         | `TELEGRAM_DEFAULT_CHAT_ID`       | Default Telegram destination           |
| `ADMIN-PASSPHRASE`                 | `ADMIN_PASSPHRASE`               | Admin console protection               |
| `GRAFANA-BASIC-AUTH`               | `GRAFANA_BASIC_AUTH`             | Grafana ingress username/password      |
| `OTEL-EXPORTER-OTLP-HEADERS`       | `OTEL_EXPORTER_OTLP_HEADERS`     | OTEL collector authentication headers  |
| `SENTRY-DSN`                       | `SENTRY_DSN`                     | Sentry ingest DSN                      |
| `ACR-USERNAME` *(fallback only)*   | `ACR_USERNAME`                   | Container registry username            |
| `ACR-PASSWORD` *(fallback only)*   | `ACR_PASSWORD`                   | Container registry password            |

> **Naming convention:** keep Key Vault secret names uppercase with dashes
> (`SERVICE-SETTING`) so translation to environment variables (`SERVICE_SETTING`)
> stays deterministic.

## Operational Guidelines

- **Managed identity first.** Use system-assigned managed identities for App
  Service → Key Vault and App Service → ACR to avoid persisting long-lived
  credentials. Only surface `ACR_*` or storage account keys when managed
  identity cannot be used.
- **Single source of truth.** When adding a new environment variable, update
  this table and create the Key Vault secret before merging code that consumes
  it.
- **Local development.** Mirror the same variable names in `.env.dev` and populate a
  private `.env` (copy `.env.example`). Sensitive production values must never be
  committed to source control.
- **Auditing.** Review Key Vault diagnostic logs quarterly to ensure no unused
  secrets linger and that rotation cadence meets security guidelines.

For guidance on wiring managed identities and App Service configuration, see
`docs/operations/managed_identity.md`.

### Tooling

- `scripts/check_secrets.py` — quick validation that your local environment (or
  `.env.dev`) contains values for every documented secret.
- `scripts/kv_sync_from_env.zsh` — publish non-empty entries from a `.env` file
  to Azure Key Vault:

  ```bash
  ./scripts/kv_sync_from_env.zsh <key-vault-name> .env.dev
  ```

  The script mirrors the mapping above, skipping empty values and reporting which
  secrets were set. Use it after rotating keys or onboarding a new environment.
- `pip-audit` — run during CI to detect vulnerable dependencies in both runtime
  and development requirement sets.

### Rotation & Sign-off

- **Cadence:** rotate production secrets (broker, database, storage, telemetry)
  quarterly or after any credential exposure/personnel change. Update Key Vault
  first, then promote the new values via App Service configuration.
- **Process:** log each rotation in Confluence with date, operator, affected
  services, and links to the corresponding Jira ticket and deployment run.
- **Validation:** run the CI pipelines (`ruff`, `bandit`, `pip-audit`, `pytest`)
  and perform a smoke test on the deployed environment to ensure new secrets are
  applied.
- **Approval:** require dual sign-off (initiator + reviewer) for high-impact
  secrets (broker, Postgres). Record the approvals in the Jira rotation ticket.
