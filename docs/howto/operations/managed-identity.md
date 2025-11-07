# How to manage Azure managed identities

## Prerequisites

- Contributor access to the Azure subscription/resource group.
- Azure CLI configured with the correct subscription.
- Key Vault with required secrets (`docs/reference/secrets.md`).

## Procedure

1. **API App Service identity**
   - Enable the system-assigned identity.
   - Assign roles:
     - Key Vault `Secrets User` on the project vault.
     - Storage account `Storage Blob Data Reader` (or Contributor if writes are needed).
     - Azure Container Registry `AcrPull`.
     - Database login mapped to the required Postgres role.

2. **UI/Streamlit App Service identity**
   - Mirror the API permissions; for read-only dashboards, grant limited database roles (`SELECT` on analytics views).

3. **GitHub Actions federated identity**
   - Configure OpenID Connect → Azure AD application.
   - Grant `AcrPush` (or `AcrPull`) and `Secrets User` permissions.
   - Optional: temporary role assignment on Postgres for Alembic migrations.

4. **Database migration role**
   - Create a dedicated Postgres role (e.g., `ai_trader_migrator`).
   - Map App Service and CI identities to this role using Azure AD authentication.
   - Example:
     ```bash
     az postgres flexible-server ad-admin set \
       --resource-group ai-trader-rg \
       --name ai-trader-db \
       --display-name "AzureAD Admin" \
       --object-id <AAD-ADMIN-OBJECT-ID>
     ```
     ```sql
     CREATE ROLE ai_trader_migrator WITH LOGIN;
     GRANT ALL ON SCHEMA market, trading, backtest, analytics, storage TO ai_trader_migrator;
     ```

5. **Apply Key Vault references**
   - App Service: `@Microsoft.KeyVault(SecretUri=...)` for each secret.
   - Container Apps: `keyvaultref:` URIs. Use versionless URIs unless a fixed version is required.

## Verification

- [ ] `az webapp identity show` returns the expected principal IDs for API/UI apps.
- [ ] `az account get-access-token --resource ...` succeeds when run from the managed identity context.
- [ ] Key Vault access policies/role assignments show the identities listed above.
- [ ] Postgres role mappings exist for `ai_trader_migrator` and are current.

## References

- Azure managed identity docs: <https://learn.microsoft.com/azure/active-directory/managed-identities-azure-resources/overview>
- `docs/reference/secrets.md`
