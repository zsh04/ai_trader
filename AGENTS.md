# AI Trader — Coding Agent Guide

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

## Coding Rules
- Use snake_case for files/functions, PascalCase for classes.
- New modules require type hints and matching tests.
- Avoid circular imports—prefer dependency injection.
- Structured logging only: `logger = logging.getLogger(__name__)`; use
  `logging_context(request_id=...)` when handling requests/tasks.
- Secrets live in Key Vault. Copy `.env.example` locally; never commit real values.

## Development Workflow
```bash
./scripts/dev.sh mkvenv     # create/refresh .venv + deps
./scripts/dev.sh install    # reinstall deps
./scripts/dev.sh lint       # ruff + bandit + pip-audit (matches CI)
./scripts/dev.sh test       # pytest
./scripts/dev.sh fmt        # black
```

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
- Post-deploy: reset Telegram webhook if relevant.

## Quick Test Targets
```bash
pytest tests/db -q
pytest tests/probability/test_pipeline.py -q
```

## References
- docs/howto/operations/observability.md
- docs/howto/operations/azure-backup.md
- docs/explanations/architecture/backtesting.md
