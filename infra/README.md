# Infra Notes (Azure)

- **Runtime**: App Service (Linux container). Set `WEBSITES_PORT=8000`, `PORT=8000`.
- **Identity**: Enable **User-Assigned Managed Identity** for Key Vault access.
- **Secrets**: Store in **Key Vault**; grant `get/list` to the web app identity.
- **Postgres**: Azure Database for PostgreSQL Flexible Server (B1ms). Enforce SSL.
- **Networking**: Optional VNet Integration + Private Endpoints (Blob, Postgres, Key Vault).
- **Scheduling**: GitHub Actions cron → call app webhooks:
  - `/tasks/premarket-scan` (04:00 PT)
  - `/tasks/watchlist-finalize` (06:15 PT)
  - `/tasks/refresh` (09:35, 11:30, 13:30 PT)
  - `/tasks/afterhours-scan` (16:05 PT)
  - `/tasks/retrain` (17:30 PT)