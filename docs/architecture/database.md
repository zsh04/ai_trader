# Database Architecture

The trading platform is backed by **Azure Database for PostgreSQL Flexible Server** with
five logical schemas:

| Schema     | Purpose                                                             |
|------------|---------------------------------------------------------------------|
| `market`   | Symbol master data, vendor credentials, OHLCV snapshots, corp actions |
| `trading`  | Orders, fills, positions, equity time-series, risk events           |
| `backtest` | Strategy runs, metrics, equity curves, artifact references          |
| `analytics`| Daily aggregates and reporting snapshots                            |
| `storage`  | Metadata for Blob artifacts (parquet, reports, models)              |

### ORM Models

The SQLAlchemy models live in `app/db/models.py` with shared mixins for timestamps.
Repositories under `app/db/repositories/` provide domain-specific helpers for
inserts, upserts, and query patterns used by the DAL, backtest engine, and
monitoring dashboard.

The initial Alembic revision (`migrations/versions/337e81e1d35c_initial_schema.py`)
materialises the schemas, tables, and indexes. Run

```bash
alembic upgrade head
```

after configuring `DATABASE_URL` to bootstrap an environment. The migration is
idempotent and assumes TimescaleDB/JSONB support available in the Flexible Server.

### Data Flow Highlights

- `MarketDataDAL` persists historical OHLCV to `market.price_snapshots` alongside
  cached parquet files.
- Streamlit dashboard reads from `trading.equity_snapshots` and `trading.fills`
  via the repository layer (no raw SQL).
- Backtest runs store configuration and metrics into the `backtest` schema and
  register produced artifacts in `storage.artifacts` for blob retrieval.

See `docs/architecture/PHASE3_BACKTESTING.md` for strategy-specific persistence
details. Secrets, Key Vault conventions, and managed identity guidance now live under
`docs/ops/` for operational reference.
