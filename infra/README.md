# Infra Notes (Azure)

- **Runtime**: App Service (Linux container). Set `WEBSITES_PORT=8000`, `PORT=8000`.
- **Identity**: Enable **User-Assigned Managed Identity** for Key Vault access.
- **Secrets**: Store in **Key Vault**; grant `get/list` to the web app identity.
- **Postgres**: Azure Database for PostgreSQL Flexible Server (B1ms). Enforce SSL.
- **Networking**: Optional VNet Integration + Private Endpoints (Blob, Postgres, Key Vault).
- **Scheduling**: Use GitHub Actions (or Azure Automation) to hit the REST API you expose for housekeeping (e.g., `/router/run` for dry runs, `/watchlists` to pin the next session’s basket). No more `/tasks/*` helpers.
