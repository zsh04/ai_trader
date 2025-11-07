# How to run the automated test suite

## Prerequisites

- Python 3.12+ with `venv` support (match `.python-version`).
- Local checkout of this repository with `./scripts/dev.sh` executable.
- Optional: Docker (if you plan to run integration tests that hit external services locally).

## Procedure

1. **Set up the environment**
   - Create or refresh the virtual environment: `python -m venv .venv && source .venv/bin/activate`.
   - Install runtime + dev dependencies: `pip install -r requirements.txt -r requirements-dev.txt`.
2. **Run fast feedback commands**
   - Lint: `ruff check .`.
   - Unit tests: `pytest tests/unit -q`.
   - These commands are also wrapped by `./scripts/dev.sh lint` and `./scripts/dev.sh test` if you prefer the scripted entrypoints.
3. **Execute DAL / backtest suites**
   - `pytest tests/dal tests/backtest -q` exercises MarketDataDAL vendors, probabilistic agents, and breakout harness logic.
   - Async fixtures default to asyncio via `anyio_backend`; override locally only if you know the implications.
4. **Full CI parity run**
   - `pytest -q` from repo root (or `./scripts/dev.sh test`) mirrors the GitHub Actions job. Ensure this completes before pushing.
5. **Security lint**
   - API pipeline command: `bandit --severity-level medium --confidence-level low -r app scripts tests`.
   - UI pipeline (once Streamlit UI ships) runs `bandit --severity-level medium --confidence-level low -r app scripts ui`.
   - Treat new Bandit findings as blockers unless explicitly triaged.

## Verification

- [ ] `ruff check .` exits 0.
- [ ] `pytest -q` exits 0 with no unexpected skips; `tests/dal` and `tests/backtest` pass locally.
- [ ] `bandit --severity-level medium --confidence-level low -r app scripts tests` reports only suppressed/known low issues.
- [ ] Git pre-push hook (if enabled) or CI dry run shows green statuses for lint, tests, and security.

## References

- `docs/howto/operations/ci-cd.md` for pipeline expectations.
- `README.md` (Testing section) for strategy-specific targets and quick commands.
