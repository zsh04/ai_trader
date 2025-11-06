# Testing Guide

Use the same virtual environment that powers local development (`python -m venv .venv && source .venv/bin/activate`). Install dependencies via `pip install -r requirements.txt`.

## Core commands

```bash
ruff check .
./.venv/bin/pytest -q
```

`pytest` picks up environment defaults from `tests/conftest.py`, including setting `PYTEST_CURRENT_TEST` and configuring fake Telegram adapters so the suite never reaches real APIs.

## Async runtime note

AnyIO-powered tests are pinned to the built-in asyncio event loop through the shared `anyio_backend` fixture in `tests/conftest.py`. This avoids optional Trio dependencies while still exercising async DAL flows. If you need to experiment with alternative backends locally, override that fixture within your test module, but always run the standard suite with the default asyncio backend before publishing a PR.

## Smoke vs full suite

- `./.venv/bin/pytest tests/unit -q` for fast iterations.
- `./.venv/bin/pytest tests/dal tests/backtest -q` to validate the probabilistic data layer and backtest harness.

CI runs the full suite with `-q`; ensure it passes locally to avoid surprises.
### Security lint

CI runs Bandit with medium-severity focus. For the API workflow we call `bandit --severity-level medium --confidence-level low -r app scripts tests`; the UI workflow uses the same flags but targets `app scripts ui`. This keeps deploy pipelines quiet while still failing builds on meaningful issues.
