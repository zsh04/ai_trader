# Codebase Health Checklist

Living checklist derived from the November 2025 baseline review. Update this
document as items are completed or reprioritised. Use Warp terminal + MCP
connections (Jira, GitHub, Confluence, Linear) to log issues and track progress
once tasks graduate from this checklist.

## Architecture & Code Hygiene

- [x] Sweep and remove legacy imports/modules (e.g., old watchlist helpers,
      unused telemetry adapters).
- [x] Wire MarketDataDAL outputs into probabilistic strategies/backtest engine.
- [x] Document final DAL/strategy pipeline in architecture notes.

## Dependencies & Tooling

- [x] Split runtime vs dev/test dependencies (requirements vs extras/lockfile).
- [x] Ensure dev tooling (`ruff`, `black`, `bandit`) invoked via `scripts/dev.sh`
      or CI targets.

## Testing & CI

- [x] Update GitHub Actions to run lint, `pytest`, and Alembic dry-run on every PR.
- [x] Resolve full-suite pytest import issues (feature flags for optional
  services) and enable in CI.
- [x] Add snapshot/backtest regression tests once probabilistic wiring complete.

## Configuration & Secrets

- [x] Replace checked-in real secrets in `.env` with placeholders; rely on Key
      Vault references for deployment.
- [x] Add automated check to ensure `.env` is never committed on new branches.

## Security

- [x] Integrate `bandit` (or equivalent) into CI pipeline.
- [x] Run dependency scanning (pip-audit/Snyk) and track remediation items.
- [x] Document secret rotation cadence and sign-off process in operations runbook.

## Observability

- [x] Standardise Loguru → structured logging fields; ensure OTEL spans/metrics
      instrumentation consistent across services.
- [x] Document Application Insights / collector deployment steps and health
      verification procedure.

## Operations & Infrastructure

- [x] Configure Azure Database backup policy and document restore drill.
- [x] Establish migration role using managed identity; update runbooks.
- [x] Add build/deploy pipeline to run new Docker build scripts (`build_api.sh`,
      `build_ui.sh`) prior to release.

## Project Progress Tracking

- [x] Create Jira epic + linked GitHub issues for remaining phase work (DAL
      integration, strategy updates, risk agent, UI polish).
- [x] Update phase progress percentages in project plan after major milestones
      (see `docs/operations/project_progress.md`).

---

**How to use:** Review this checklist during weekly planning. When an item is
ready to be executed, create the appropriate issue in Jira/GitHub/Linear via
Warp's MCP integrations, then mark the box here once complete.\*\*\*
