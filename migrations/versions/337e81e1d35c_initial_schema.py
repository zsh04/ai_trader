"""initial schema

Revision ID: 337e81e1d35c
Revises:
Create Date: 2025-10-28 13:59:41.172232

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "337e81e1d35c"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schemas
    for schema in ("market", "trading", "backtest", "analytics", "storage"):
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

    timestamp = sa.DateTime(timezone=True)
    jsonb = postgresql.JSONB

    def numeric(precision: int, scale: int) -> sa.Numeric:
        return sa.Numeric(precision, scale)

    # market.symbols
    op.create_table(
        "symbols",
        sa.Column("symbol", sa.String(length=24), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("asset_class", sa.String(length=32), nullable=True),
        sa.Column("primary_exchange", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=True,
            server_default=sa.text("'active'"),
        ),
        sa.Column("figi", sa.String(length=24), nullable=True),
        sa.Column("isin", sa.String(length=24), nullable=True),
        sa.Column("metadata", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        schema="market",
    )

    op.create_table(
        "vendor_credentials",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("vendor", sa.String(length=32), nullable=False),
        sa.Column("api_key", sa.Text, nullable=True),
        sa.Column("metadata", jsonb(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("vendor", name="uq_vendor_credentials_vendor"),
        schema="market",
    )

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "symbol",
            sa.String(length=24),
            sa.ForeignKey("market.symbols.symbol"),
            nullable=False,
        ),
        sa.Column("vendor", sa.String(length=32), nullable=False),
        sa.Column("ts_utc", timestamp, nullable=False),
        sa.Column("open", numeric(18, 6), nullable=True),
        sa.Column("high", numeric(18, 6), nullable=True),
        sa.Column("low", numeric(18, 6), nullable=True),
        sa.Column("close", numeric(18, 6), nullable=True),
        sa.Column("volume", numeric(24, 4), nullable=True),
        sa.Column("vwap", numeric(18, 6), nullable=True),
        sa.Column("trade_count", sa.Integer, nullable=True),
        sa.Column("features", jsonb(), nullable=True),
        sa.Column("ingestion_latency_ms", sa.Integer, nullable=True),
        sa.Column(
            "ingestion_ts", timestamp, nullable=False, server_default=sa.func.now()
        ),
        schema="market",
    )
    op.create_index(
        "ix_price_snapshots_symbol_ts",
        "price_snapshots",
        ["symbol", "ts_utc"],
        unique=False,
        schema="market",
    )

    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "symbol",
            sa.String(length=24),
            sa.ForeignKey("market.symbols.symbol"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("effective_date", timestamp, nullable=False),
        sa.Column("ratio", numeric(18, 6), nullable=True),
        sa.Column("metadata", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        schema="market",
    )
    op.create_index(
        "ix_corporate_actions_symbol_effective",
        "corporate_actions",
        ["symbol", "effective_date"],
        unique=False,
        schema="market",
    )

    # trading tables
    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column(
            "symbol",
            sa.String(length=24),
            sa.ForeignKey("market.symbols.symbol"),
            nullable=False,
        ),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("time_in_force", sa.String(length=16), nullable=True),
        sa.Column("qty", numeric(18, 6), nullable=False),
        sa.Column(
            "filled_qty", numeric(18, 6), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("limit_price", numeric(18, 6), nullable=True),
        sa.Column("stop_price", numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("submitted_at", timestamp, nullable=True),
        sa.Column("raw_payload", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        schema="trading",
    )
    op.create_index(
        "ix_orders_symbol_created_at",
        "orders",
        ["symbol", "created_at"],
        unique=False,
        schema="trading",
    )

    op.create_table(
        "fills",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "order_id",
            sa.String(length=64),
            sa.ForeignKey("trading.orders.id"),
            nullable=False,
        ),
        sa.Column(
            "symbol",
            sa.String(length=24),
            sa.ForeignKey("market.symbols.symbol"),
            nullable=False,
        ),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", numeric(18, 6), nullable=False),
        sa.Column("price", numeric(18, 6), nullable=False),
        sa.Column("fee", numeric(18, 6), nullable=True),
        sa.Column("pnl", numeric(18, 6), nullable=True),
        sa.Column("filled_at", timestamp, nullable=False),
        sa.Column("raw_payload", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        schema="trading",
    )
    op.create_index(
        "ix_fills_symbol_filled_at",
        "fills",
        ["symbol", "filled_at"],
        unique=False,
        schema="trading",
    )

    op.create_table(
        "positions",
        sa.Column(
            "symbol",
            sa.String(length=24),
            sa.ForeignKey("market.symbols.symbol"),
            primary_key=True,
        ),
        sa.Column("net_qty", numeric(18, 6), nullable=False),
        sa.Column("avg_price", numeric(18, 6), nullable=False),
        sa.Column(
            "realized_pnl", numeric(18, 6), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "unrealized_pnl",
            numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("leverage", numeric(10, 4), nullable=True),
        sa.Column("metadata", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        schema="trading",
    )

    op.create_table(
        "equity_snapshots",
        sa.Column("ts_utc", timestamp, primary_key=True),
        sa.Column("equity", numeric(20, 4), nullable=False),
        sa.Column("cash", numeric(20, 4), nullable=True),
        sa.Column("pnl_day", numeric(20, 4), nullable=True),
        sa.Column("drawdown", numeric(10, 4), nullable=True),
        sa.Column("leverage", numeric(10, 4), nullable=True),
        sa.Column("metadata", jsonb(), nullable=True),
        schema="trading",
    )

    op.create_table(
        "risk_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "symbol",
            sa.String(length=24),
            sa.ForeignKey("market.symbols.symbol"),
            nullable=True,
        ),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("value", numeric(18, 6), nullable=False),
        sa.Column("threshold", numeric(18, 6), nullable=True),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'info'"),
        ),
        sa.Column("triggered_at", timestamp, nullable=False),
        sa.Column("details", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        schema="trading",
    )
    op.create_index(
        "ix_risk_events_symbol_triggered",
        "risk_events",
        ["symbol", "triggered_at"],
        unique=False,
        schema="trading",
    )

    # backtest schema
    op.create_table(
        "strategy_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("parameters", jsonb(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("started_at", timestamp, nullable=True),
        sa.Column("completed_at", timestamp, nullable=True),
        sa.Column("result_path", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("metrics_summary", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        schema="backtest",
    )
    op.create_index(
        "ix_strategy_runs_strategy_started",
        "strategy_runs",
        ["strategy_name", "started_at"],
        unique=False,
        schema="backtest",
    )

    op.create_table(
        "strategy_run_metrics",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("backtest.strategy_runs.id"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("metric_value", numeric(18, 6), nullable=False),
        sa.Column("metadata", jsonb(), nullable=True),
        schema="backtest",
    )
    op.create_index(
        "ix_strategy_run_metrics_run_metric",
        "strategy_run_metrics",
        ["run_id", "metric_name"],
        unique=False,
        schema="backtest",
    )

    op.create_table(
        "strategy_run_equity",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("backtest.strategy_runs.id"),
            nullable=False,
        ),
        sa.Column("ts_utc", timestamp, nullable=False),
        sa.Column("equity", numeric(20, 4), nullable=False),
        sa.Column("metadata", jsonb(), nullable=True),
        schema="backtest",
    )
    op.create_index(
        "ix_strategy_run_equity_run_ts",
        "strategy_run_equity",
        ["run_id", "ts_utc"],
        unique=False,
        schema="backtest",
    )

    # analytics
    op.create_table(
        "daily_metrics",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("metric_date", sa.Date, nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("metric_value", numeric(18, 6), nullable=False),
        sa.Column("metadata", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "metric_date", "metric_name", name="uq_daily_metrics_date_name"
        ),
        schema="analytics",
    )

    # storage
    op.create_table(
        "artifacts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("uri", sa.Text, nullable=False),
        sa.Column("checksum", sa.String(length=72), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("metadata", jsonb(), nullable=True),
        sa.Column(
            "created_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", timestamp, server_default=sa.func.now(), nullable=False
        ),
        schema="storage",
    )
    op.create_index(
        "ix_artifacts_owner_type",
        "artifacts",
        ["owner_type", "owner_id"],
        unique=False,
        schema="storage",
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_index("ix_artifacts_owner_type", table_name="artifacts", schema="storage")
    op.drop_table("artifacts", schema="storage")

    op.drop_table("daily_metrics", schema="analytics")

    op.drop_index(
        "ix_strategy_run_equity_run_ts",
        table_name="strategy_run_equity",
        schema="backtest",
    )
    op.drop_table("strategy_run_equity", schema="backtest")

    op.drop_index(
        "ix_strategy_run_metrics_run_metric",
        table_name="strategy_run_metrics",
        schema="backtest",
    )
    op.drop_table("strategy_run_metrics", schema="backtest")

    op.drop_index(
        "ix_strategy_runs_strategy_started",
        table_name="strategy_runs",
        schema="backtest",
    )
    op.drop_table("strategy_runs", schema="backtest")

    op.drop_index(
        "ix_risk_events_symbol_triggered", table_name="risk_events", schema="trading"
    )
    op.drop_table("risk_events", schema="trading")

    op.drop_table("equity_snapshots", schema="trading")

    op.drop_table("positions", schema="trading")

    op.drop_index("ix_fills_symbol_filled_at", table_name="fills", schema="trading")
    op.drop_table("fills", schema="trading")

    op.drop_index("ix_orders_symbol_created_at", table_name="orders", schema="trading")
    op.drop_table("orders", schema="trading")

    op.drop_index(
        "ix_corporate_actions_symbol_effective",
        table_name="corporate_actions",
        schema="market",
    )
    op.drop_table("corporate_actions", schema="market")

    op.drop_index(
        "ix_price_snapshots_symbol_ts", table_name="price_snapshots", schema="market"
    )
    op.drop_table("price_snapshots", schema="market")

    op.drop_table("vendor_credentials", schema="market")
    op.drop_table("symbols", schema="market")

    for schema in ("storage", "analytics", "backtest", "trading", "market"):
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
