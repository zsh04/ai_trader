# Operations runbook

## Prerequisites

- Access to Azure subscription resources (App Service, Blob Storage, PostgreSQL Flexible Server).
- PM2 installed on any long-running VM used for log rotation.
- Managed identity and Key Vault references configured (see `docs/howto/operations/managed-identity.md`).

## Daily schedule (Pacific Time)

| Time | Action |
|------|--------|
| 03:58 | Start container / confirm App Service is running |
| 04:00 | Premarket scan (rough watchlist) |
| 06:15 | Finalize opening watchlist |
| 09:25 | Warm-up; 09:30 regular session open |
| 09:35 / 11:30 / 13:30 | Intraday refresh cycles |
| 16:05 | After-hours scan |
| 17:30 | Retrain (when enabled) |
| 18:00 | Reports / summaries |

## Azure operations checklist

1. **App Service (API & UI)**
   - Linux container, Managed Identity enabled, `WEBSITES_PORT` aligned with uvicorn port.
2. **Blob Storage**
   - Containers `trader-data`, `trader-models`; rotate SAS tokens if MSI isn’t used.
3. **PostgreSQL Flexible Server**
   - Tier `B1ms`, storage 32 GB, SSL required. Ensure VNet integration or outbound IP allowlisting is configured.

## Post-deployment steps

1. Tail App Service logs until the new container reports healthy:
   ```bash
   az webapp log tail -n "$WEBAPP_NAME" -g "$RESOURCE_GROUP"
   ```
2. Flush local PM2 logs if applicable:
   ```bash
   pm2 flush ai-trader
   ```
3. Hit `/health/live` and `/health/ready` and confirm HTTP 200.

## References

- `docs/howto/operations/observability.md`
- `docs/howto/operations/azure-backup.md`
