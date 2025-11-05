# Changelog

## Unreleased

### Changed

- Standardized all logging to use `loguru`.

**Modified Files:**

- `app/utils/http.py`
- `app/providers/alpaca_provider.py`
- `app/providers/yahoo_provider.py`
- `app/domain/watchlist_service.py`
- `app/execution/alpaca_client.py`
- `app/execution/router.py`
- `app/adapters/telemetry/__init__.py`
- `app/adapters/telemetry/logging.py`
- `app/adapters/telemetry/loguru.py`
- `app/adapters/db/postgres.py`
- `app/adapters/market/alpaca_client.py`
- `app/adapters/notifiers/telegram.py`
- `app/scanners/watchlist_builder.py`
- `app/api/routes/telegram.py`
- `app/api/routes/tasks.py`
- `app/data/data_client.py`
- `app/sessions/session_clock.py`
- `app/backtest/run_breakout.py`
- `app/backtest/metrics.py`
- `app/backtest/__init__.py`
- `app/features/mtf_aggregate.py`
- `app/features/indicators.py`
- `app/main.py`
- `app/core/timeutils.py`
- `app/sources/textlist_source.py`
- `app/sources/__init__.py`
- `app/agent/sizing.py`
- `app/agent/risk.py`
- `tests/utils/test_http.py`
- `tests/providers/test_yahoo_provider.py`
- `pyproject.toml`
- `requirements.txt`
