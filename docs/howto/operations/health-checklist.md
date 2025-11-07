# How to run the daily health checklist

## Prerequisites

- Access to Azure Portal (App Service, PostgreSQL Flexible Server, Storage account) with at least reader rights.
- GitHub access to view latest Actions runs and issue trackers.
- Key Vault `Get` permissions to confirm secret versions when needed.
- Local shell with `az`, `gh`, and repository scripts available (`./scripts/dev.sh`).

## Procedure

1. **Confirm platform health**
   - Run `az webapp show -n "$AZURE_WEBAPP_NAME" -g "$AZURE_RESOURCE_GROUP" --query state -o tsv`.
   - Check `/health/ready` via `curl` or browser; expect HTTP 200.
   - For the UI App Service (if deployed separately), repeat the same checks.
2. **Verify database and storage**
   - `az postgres flexible-server show -n "$POSTGRES_NAME" -g "$RESOURCE_GROUP" --query state` should be `Ready`.
   - Inspect backup policy timestamps: `az postgres flexible-server backup list ...`.
   - Ensure Blob containers (`trader-data`, `trader-models`) report recent writes: `az storage blob list ... --num-results 5`.
3. **Review observability signals**
   - Open Application Insights (or Grafana dashboard) and confirm the following last-hour metrics stay within SLOs: request success rate > 99%, P50 latency < 500 ms, error logs < 5/min.
   - Tail OTEL collector logs for reconnect warnings.
4. **Check CI/CD + security gates**
   - `gh run list -L 5` should show the latest `ci-api`/`ci-ui` workflows succeeded.
   - Review dependency scans (pip-audit) and security lint (Bandit) results for new findings; file issues as needed.
5. **Record status and deltas**
   - Update `research-docs/health-checklist.md` with any blockers or follow-ups.
   - If incidents were observed, open tasks in Jira (`phase-p2-backtesting` epic) and link them in the research notes.

## Verification

- [ ] API and UI `/health/ready` endpoints return 200 with current git SHA in headers/logs.
- [ ] Database and storage services report `Ready` with backup snapshots < 24 hours old.
- [ ] Observability dashboards show SLO-compliant latency/error metrics.
- [ ] Latest CI runs (`ci-api`, `ci-ui`) succeeded and dependency scans are green.
- [ ] Health checklist notes updated with today’s date and any action items.

## References

- `docs/howto/operations/runbook.md` for the daily schedule.
- `docs/howto/operations/observability.md` for dashboard setup steps.
- `docs/explanations/operations/roadmap.md` for current milestone context.
