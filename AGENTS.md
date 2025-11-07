# AI Trader — Agent Operating Protocol (AGENTS.md)

## Load these first (always)

- `.docs-policy.json` — canonical rules (Diátaxis, front-matter, style)
- `docs/documentation_guidelines_rules.md` — local summary/pointer
  > If anything here conflicts with policy, **policy wins**.

## Architecture Snapshot

```
app/
 ├── adapters/         # Data access (Postgres, Blob)
 ├── agent/            # Risk, sizing, trading logic
 ├── api/              # FastAPI routes
 ├── backtest/         # Engine, metrics, CLI
 ├── core/             # Models, utilities
 ├── probability/      # Probabilistic DAL helpers
 ├── providers/        # Market data connectors
 ├── scanners/         # Watchlist/scan generation
 ├── strats/           # Breakout, momentum, etc.
 └── tests/            # Unit / integration suites
```

## Project Primer

- **Mission:** Probabilistic, risk‑first autonomous trading—start in paper, promote to live when guardrails pass.
- **Constraints:** Infra ≤ $500/mo; seed capital $250–$500; prefer serverless/Container Apps where practical.
- **Vendors/Broker:** Data via DAL (Alpha Vantage, Finnhub, Twelve Data); broker = Alpaca (paper → live).
- **Guardrails:** 1% risk/trade, 5% daily drawdown halt; bracket orders; reconciliation required.
- **Canonical events:** PriceBar, Quote, Signal, ProbVector, RiskDecision, OrderIntent, OrderAck, Fill, PnlUpdate.
- **Environments:** dev → paper → live; shadow + canary before promotion; feature flags per ring.

## Coding Rules

- Use snake_case for files/functions, PascalCase for classes.
- New modules require type hints and matching tests.
- Avoid circular imports—prefer dependency injection.
- Structured logging only: `logger = logging.getLogger(__name__)`; use
  `logging_context(request_id=...)` when handling requests/tasks.
- Secrets live in Key Vault. Copy `.env.example` locally; never commit real values.

## Coding playbook

- **Versions:** Python 3.11; Node 20; target Linux x86_64.
- **Format:** black (line=88) + isort (profile=black). Run `./scripts/dev.sh fmt`.
- **Lint & type:** ruff (E,F,I; no W) + mypy (strict optional) on `app/` and `tests/`.
- **Tests:** pytest with markers `unit`, `integration`, `contract`, `smoke`; coverage gate **≥ 80%** on PRs.
- **Errors & retries:** wrap I/O with retry (3x, exponential backoff + jitter); never bare `except`; include a `request_id` in logs.
- **Logging:** structured, no PII; redact account IDs; levels: INFO (business), DEBUG (dev), WARN/ERROR (actionable).
- **Security:** secrets via Key Vault / Managed Identity; no secrets in tests; run `gitleaks` in CI.
- **Performance:** adhere to the **Performance budgets** section below.

## Documentation rules (Diátaxis + Google style)

- **Pick one type:** tutorial | how-to | reference | explanation (no mixing)
- **Front-matter (required at top):**

  ```yaml
  ---
  title: ""
  doc_type: tutorial|how-to|reference|explanation
  audience: beginner|intermediate|advanced
  product_area: trading|data|backtest|ui|ops|risk
  last_verified: YYYY-MM-DD
  toc: true
  ---
  ```

- **Style:** Google Developer Documentation (second person, active voice, short sentences)
- **Links:** relative; include a **“See also”** section
- **Mermaid:** `graph | sequenceDiagram | stateDiagram-v2 | classDiagram` (≤25 nodes)
- **Folders:** must match `doc_type`

## Development Workflow

```bash
./scripts/dev.sh mkvenv     # create/refresh .venv + deps
./scripts/dev.sh install    # reinstall deps
./scripts/dev.sh lint       # ruff + bandit + pip-audit (matches CI)
./scripts/dev.sh test       # pytest
./scripts/dev.sh fmt        # black
```

## Branching & releases

- **Flow:** trunk‑based; short‑lived feature branches (`feat/*`, `fix/*`, `docs/*`); squash merge.
- **Commits:** Conventional Commits (e.g., `feat(api): add bracket orders`).
- **Tags:** semantic versioning `vMAJOR.MINOR.PATCH` after green CI; release notes generated from commits.

## Testing matrix

- **unit:** pure functions/components (fast, isolated).
- **integration:** DB/broker sandbox, DAL adapters.
- **contract:** API schemas & canonical events (OpenAPI/JSON Schema).
- **smoke:** post‑deploy health & happy‑path trades.
- **Gate:** coverage **≥ 80%**; smoke must pass before promotion.

## Dependencies & updates

- **Pin & lock:** maintain `requirements.lock`/`uv.lock` (or equivalent). No unpinned prod deps.
- **Updater:** Renovate manages GitHub Actions and dependency bumps (automerge for safe updates).
- **Review:** avoid unmaintained or risky libs (no `eval`‑style dynamic code loaders); prefer well‑supported packages.
- **Security:** run `pip‑audit`/`npm audit` in CI; patch high/critical promptly.

## Backtesting / Probabilistic Pipeline

```bash
python -m app.backtest.run_breakout \
  --symbol AAPL --start 2021-01-01 \
  --use-probabilistic --regime-aware-sizing
```

This pulls MarketDataDAL probabilistic features (see `app/probability/pipeline.py`).

## CI / Deployment Highlights

- GitHub Actions run linting, bandit, pip-audit, Alembic dry-run, and the full test suite on every PR.
- API/UI images are built via `scripts/build_api.sh` / `scripts/build_ui.sh` during `main` deployments.
- Post-deploy: run health checks and smoke tests; Telegram is deprecated.

## Quick Test Targets

```bash
pytest tests/db -q
pytest tests/probability/test_pipeline.py -q
```

## Performance budgets

- **API latency:** p95 ≤ **200 ms**.
- **Decision path:** p99 ≤ **30 ms**.
- **Broker RTT:** p99 ≤ **150 ms**.
- Enforce via smoke/trace checks and fail the deploy if breached.

## Security & compliance

- No secrets in code or docs; use placeholders and environment variables
- **Public** docs go in `docs/`; **internal** docs go in `internal/`
- Capture significant decisions as ADRs under `docs/explanation/adr/`
- **Privacy:** no PII in logs; hash or drop account identifiers.
- **Retention:** 30d app logs, 90d audit trails; rotate daily.

## Risk & execution guardrails

- Pre-trade checks (exposure caps, per-name/sector limits)
- Hard caps: ~**1% risk/trade**, **5% daily drawdown halt**
- Use bracket orders for entries; reconcile positions after fills
- Maintain a kill-switch / SafeMode and document it in runbooks

## Definitions of Done (DoD)

- **Docs DoD:** valid front-matter, Diátaxis-pure, Google style, relative links, **See also**, `last_verified` updated
- **Code DoD:** format/lint/tests green; tests for new behavior; docs updated; ADR added/updated if behavior changes

## Common agent prompts — Engineering

- **How-to**
  > Read `.docs-policy.json` and `AGENTS.md`. Create a **how-to** about _Configure bracket orders on Alpaca (paper)_. Use required front-matter, Google style, relative links, a Mermaid sequence, and a **Related** section.
- **Architecture explanation**
  > Read `.docs-policy.json` and `AGENTS.md`. Create an **explanation** named _System Architecture_ with component + sequence Mermaid, non-functional requirements, failure modes, dependencies, and **See also**.
- **Code change**
  > Implement idempotent order keys in `app/agent/execution.py`. Add tests in `tests/agent/test_execution.py`. Run fmt/lint/tests. If semantics change, add an ADR and update reference docs.

## Common agent prompts — Project Management (Agile/PMP)

_(Files live under `internal/project-docs/`.)_

- **Project Charter**
  > Create `internal/project-docs/charter.md` using PM front-matter and sections (Purpose, Scope, Success Criteria, Stakeholders & RACI, Risks, Milestones).
- **Sprint Plan**
  > Create `internal/project-docs/sprint-plan.md` with front-matter (owner, period, health). Include Sprint Goal, Scope (issue/PR links), DOR/DOD, Demo Plan, Dependencies & Risks.
- **Weekly Sprint Status**
  > Create `internal/project-docs/sprint-status.md` with front-matter. Sections: Highlights, Risks/Issues, Next, Metrics (velocity/burndown link, error budget). Use Green/Yellow/Red health.
- **Risk Register update**
  > Append to `internal/project-docs/risk-register.md` with ID, Risk, Prob, Impact, Owner, Mitigation, Status.
- **Decision log + ADR**
  > Add a row in `internal/project-docs/decision-log.md` (date, decision, link). If significant, add a new `docs/explanation/adr/00NN-*.md` using MADR (context, options, decision, consequences).

## MCP servers & tool use

Agents have access to **MCP servers via `~/.codex/config.toml`**. Prefer MCP tools over guessing—fetch files, schemas, and issues before writing docs or status.
**Common servers available:**

- `filesystem` — read project files for accurate context
- `github` — issues/PRs/labels
- `atlassian` — Confluence/Jira (internal updates)
- `docker`, `postgresql`, `sentry`, `azure`, `terraform`, `puppeteer`
- `context7` — organization-wide context injection (diagrams/guidelines/policy)

## License & compliance

- Follow repository license terms; include notices for third‑party code.
- Adhere to CODE_OF_CONDUCT.md and SECURITY.md (responsible disclosure).
- Document third‑party licenses in `THIRD_PARTY_NOTICES` if required.

## References

- docs/howto/operations/observability.md
- docs/howto/operations/azure-backup.md
- docs/explanations/architecture/backtesting.md
