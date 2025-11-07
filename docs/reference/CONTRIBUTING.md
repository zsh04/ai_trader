---
title: "Contributor Reference"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-06
toc: true
---

# Contributor Reference

## Purpose

Snapshot of expectations for external and internal contributors: environment setup, workflow, coding standards, and required checks before a pull request lands.

## Repository map

```
app/
  adapters/    # DAL connectors, messaging
  agent/       # Signal, regime, sizing logic
  api/         # FastAPI routers
  backtest/    # Engines, sweeps
  monitoring/  # Dashboards, Streamlit
  probability/ # Kalman, probabilistic DAL
  strats/      # Momentum, breakout, mean-reversion
scripts/       # Dev + CI helpers
ui/            # Streamlit console (planned)
```

## Environment setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt -r requirements-dev.txt`
3. Copy `.env.example` → `.env` for local-only values (never commit real secrets).
4. Run `./scripts/dev.sh install` to sync tooling versions.

## Workflow expectations

| Step | Command / Action | Notes |
|------|------------------|-------|
| Lint | `./scripts/dev.sh lint` | Ruff, bandit, formatting
| Tests | `./scripts/dev.sh test` | Pytest (unit + DAL/backtest)
| Format | `./scripts/dev.sh fmt` | Black, organize imports
| Docs | Update relevant Diátaxis doc + changelog | Required for config or API changes
| PR template | Fill sections (Summary, Testing, Docs) | Auto-checked in CI

## Coding standards

- Type hints required; `mypy` friendly code.
- Structured logging via `app/logging_utils.py`; no ad-hoc `print`.
- Dependency injection preferred over global imports to avoid circular references.
- Secrets loaded from Key Vault references; local `.env` limited to dev overrides.

## Git & branching

- Feature branches: `feature/<scope>`; bugfix: `fix/<issue>`.
- Rebase on `main` before raising PR.
- Squash merge with conventional commits when possible (`feat:`, `fix:`, `docs:`).

## Review checklist

- [ ] Tests cover new logic (unit/integration).
- [ ] Docs updated (Diátaxis location + CHANGELOG entry).
- [ ] No secrets or large data files committed.
- [ ] CI green (lint, test, security, Alembic dry-run).

## See also

- [How to run the automated test suite](../howto/testing.md)
- [CI/CD operations guide](../howto/operations/ci-cd.md)
- [Documentation guidelines](./doc-guidelines.md)
