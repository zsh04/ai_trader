# How to back up and restore Azure PostgreSQL Flexible Server

## Prerequisites

- Contributor access to the Azure subscription/resource group hosting `ai-trader-db`.
- Azure CLI (`az`) logged in with the correct subscription context.
- Awareness of the current Key Vault/App Service settings so any restored server can be wired back in.

## Procedure

1. **Configure retention policy**
   1. In the Azure portal, open **PostgreSQL Flexible Server → ai-trader-db**.
   2. Set **Settings → Backups → Backup retention** to 14 days and enable **Geo-redundant backup** if required.
   3. Confirm Point-in-Time Restore (PITR) shows as enabled and log the change in the service catalog.
   4. CLI alternative:
      ```bash
      az postgres flexible-server update \
        --name ai-trader-db \
        --resource-group ai-trader-rg \
        --backup-retention 14 \
        --geo-redundant-backup Enabled
      ```

2. **Run a restore drill** (quarterly)
   1. Pick a timestamp within the retention window (e.g., 24 hours earlier).
   2. Portal: **Restore** → target server `ai-trader-db-restore-<date>` with matching VNet/firewall settings.
   3. CLI alternative:
      ```bash
      az postgres flexible-server restore \
        --resource-group ai-trader-rg \
        --name ai-trader-db \
        --restore-time "2025-11-05T10:00:00Z" \
        --target-server ai-trader-db-restore-20251105
      ```
   4. Run smoke tests against the restored endpoint (`psql`, `pg_dump --schema-only`, key queries).
   5. Tear down the restored server when validation is complete to avoid cost.
   6. Document the drill (timestamp, operator, findings, issues) in Confluence/Jira.

3. **Automate monitoring**
   - Create Azure Monitor alerts on `BackupStatus` and PITR failures.
   - Optional: script a GitHub Actions/Azure Automation job that restores nightly to a sandbox and reports status.

## Verification

- [ ] Backup retention shows 14 days with PITR enabled in the portal/CLI.
- [ ] A restore drill has been executed and logged within the last quarter.
- [ ] Connection strings/Key Vault references were validated (or updated) after the drill.

## References

- Azure docs: <https://learn.microsoft.com/azure/postgresql/flexible-server/concepts-backup-restore>
- `docs/reference/secrets.md` (for Key Vault mappings)
