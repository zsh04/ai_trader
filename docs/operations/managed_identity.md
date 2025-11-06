# Managed Identity Playbook

We rely on Azure Managed Identities to eliminate static credentials wherever
possible. The following identities should be provisioned and granted access via
role assignments or Key Vault access policies.

## App Service (API) Managed Identity

- **Scope:** System-assigned identity on the API App Service.
- **Roles / Access:**
  - Key Vault `Secrets User` (or `Key Vault Reader` + `Secrets Reader`) on the
    project vault.
  - Storage account `Storage Blob Data Reader` for read access to artifacts.
  - Azure Container Registry `AcrPull` (or `AcrPush` if the service builds images).
  - Database (Postgres) login mapped to a database role with `SELECT/INSERT/UPDATE`
    permissions as required by the API.

## App Service (UI) Managed Identity

- Same baseline permissions as the API if the UI needs direct data access.
- For read-only dashboards, you can grant limited database role permissions
  (`SELECT` on analytics views).

## GitHub Actions / CI Federated Identity

- Use OpenID Connect to grant GitHub Actions a federated identity that can:
  - `AcrPush` to the container registry.
  - `Secrets User` on Key Vault for retrieving build-time secrets (if required).
  - Optional: Temporary role assignment on Postgres for migrations (see below).

## Database Migration Role

- Create a dedicated Postgres role (e.g. `ai_trader_migrator`) with privileges to
  apply Alembic migrations (DDL on `market`, `trading`, `backtest`, `analytics`,
  `storage` schemas).
- Map the App Service identity and CI identity to this role using Azure AD
  authentication or Key Vault-managed credentials. This keeps application runtime
  separate from schema management.

### Managed Identity Mapping Steps

1. Enable Azure AD authentication on the Flexible Server:
   ```bash
   az postgres flexible-server ad-admin set \
     --resource-group ai-trader-rg \
     --name ai-trader-db \
     --display-name "AzureAD Admin" \
     --object-id <AAD-ADMIN-OBJECT-ID>
   ```
2. Assign database permissions:
   ```sql
   CREATE ROLE ai_trader_migrator WITH LOGIN;
   GRANT ALL ON SCHEMA market, trading, backtest, analytics, storage TO ai_trader_migrator;
   GRANT CREATE, ALTER, DROP ON DATABASE traderdata TO ai_trader_migrator;
   ```
3. Grant App Service and CI managed identities access:
   ```bash
   az postgres flexible-server ad-admin set \
     --resource-group ai-trader-rg \
     --name ai-trader-db \
     --display-name "AI Trader API MI" \
     --object-id <APP-SERVICE-MI-OBJECT-ID>
   ```
   Use `az webapp identity show` to retrieve the object IDs. Repeat for the GitHub Actions federated identity used for migrations.

## Implementation Tips

- **Least privilege:** scope role assignments to resource groups or individual
  resources rather than subscription-wide grants.
- **Rotation:** even though managed identities rotate automatically, periodically
  verify access by running `az account get-access-token --resource ...` and
  ensuring resource operations succeed.
- **Documentation:** record role assignments and their justification alongside
  your infrastructure-as-code to keep auditors happy.

## Resource Access Matrix

| Resource                              | Needs Key Vault?               | KV Role                 | Other Roles / Notes                                                                 |
|---------------------------------------|--------------------------------|-------------------------|--------------------------------------------------------------------------------------|
| API Web App (`ai-trader-app`)         | Yes (KV refs in App Settings)  | Key Vault Secrets User  | `AcrPull` on ACR; optionally `Storage Blob Data Contributor` if you drop conn-string |
| UI Web App (`ai-trader-ui`)           | Yes (KV refs in App Settings)  | Key Vault Secrets User  | `AcrPull`                                                                             |
| OTel Container App (`ai-trader-otel`) | Yes (ACA secret reference)     | Key Vault Secrets User  | `AcrPull` on ACR                                                                     |
| Azure Container Registry              | No                             | —                       | Grant `AcrPull` to the identities above                                              |
| Azure Storage (`aitraderblobstore`)   | No (keys/tokens in KV or MI)   | —                       | Grant `Storage Blob Data Contributor` when using MI over access keys                 |
| Postgres Flexible Server              | No                             | —                       | Consider enabling AAD auth later; app can use MI → AAD token                         |
| Azure Front Door                      | No (unless BYO cert from KV)   | —                       | If custom domains need KV certs, wire those when required                            |

### Key Vault Reference Tips

- App Service references must use the `@Microsoft.KeyVault(...)` format already in
  place. Versionless URIs are fine; the platform refreshes to the latest secret.
- Azure Container Apps can reference secrets via `keyvaultref:` URIs. Use the same
  managed identity + Key Vault Secrets User role. Versionless URIs update within
  ~30 minutes; pin a version only if you need full control.

For the canonical secrets → environment variable mapping, refer to
`docs/operations/secrets.md`.
