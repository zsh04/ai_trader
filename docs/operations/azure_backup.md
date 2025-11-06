# Azure Database Backup & Restore Runbook

This runbook documents the backup policy for the AI Trader PostgreSQL Flexible Server and
how to execute a restore drill.

## 1. Backup Policy Configuration

1. Navigate to the PostgreSQL Flexible Server (`ai-trader-db`) in the Azure portal.
2. Under **Settings → Backups**, set:
   - **Backup retention**: 14 days (minimum for PITR)
   - **Geo-redundant backup**: Enabled (if business continuity requires it)
3. Confirm PITR (Point-In-Time Restore) is enabled.
4. Document the policy in the service catalog (link this runbook).

Command-line equivalent:
```bash
az postgres flexible-server update \
  --name ai-trader-db \
  --resource-group ai-trader-rg \
  --backup-retention 14 \
  --geo-redundant-backup Enabled
```

## 2. Restore Drill Procedure

1. Pick a restore point within the retention window (e.g., 24 hours ago).
2. In the portal, select **Restore** → create a new server (`ai-trader-db-restore-<date>`).
3. Set networking identical to production (VNet, firewall rules).
4. Once the restore completes:
   - Run smoke tests using the restored endpoint.
   - Verify that schema and data look correct (`psql` or `pg_dump --schema-only`).
5. Tear down the restored server to avoid extra cost.
6. Log the drill in Confluence with timestamp, operator, and findings.

CLI snippet:
```bash
az postgres flexible-server restore \
  --resource-group ai-trader-rg \
  --name ai-trader-db \
  --restore-time "2025-11-05T10:00:00Z" \
  --target-server ai-trader-db-restore-20251105
```

## 3. Verification Checklist

- [ ] Backup retention matches policy (14 days).
- [ ] Restore drill performed at least once per quarter.
- [ ] Drill documented in Confluence (link to ticket).
- [ ] Connection strings / Key Vault secrets updated if failover scenario executed.

## 4. Automation Considerations

- Monitor `BackupStatus` metrics via Azure Monitor alerts.
- Create an Azure Automation or GitHub Actions workflow to run the restore drill in a sandbox and
  post results to Confluence/Jira.

Keep this runbook updated as retention requirements or database settings change.
