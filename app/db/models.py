from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.db.postgres import Base
from app.db.mixins import TimestampMixin


class Symbol(Base, TimestampMixin):
    __tablename__ = "symbols"
    __table_args__ = (
        {"schema": "market"},
    )

    symbol: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128))
    asset_class: Mapped[str | None] = mapped_column(String(32))
    primary_exchange: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str | None] = mapped_column(String(16), default="active")
    figi: Mapped[str | None] = mapped_column(String(24))
    isin: Mapped[str | None] = mapped_column(String(24))
    attributes: Mapped[dict | None] = mapped_column("metadata", JSONB)

    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        back_populates="symbol_ref", cascade="all, delete-orphan"
    )


class VendorCredential(Base, TimestampMixin):
    __tablename__ = "vendor_credentials"
    __table_args__ = (
        UniqueConstraint("vendor", name="uq_vendor_credentials_vendor"),
        {"schema": "market"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor: Mapped[str] = mapped_column(String(32), nullable=False)
    api_key: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column("metadata", JSONB)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (
        Index("ix_price_snapshots_symbol_ts", "symbol", "ts_utc"),
        {"schema": "market"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(
        String(24), ForeignKey("market.symbols.symbol"), nullable=False
    )
    vendor: Mapped[str] = mapped_column(String(32), nullable=False)
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float | None] = mapped_column(Numeric(18, 6))
    high: Mapped[float | None] = mapped_column(Numeric(18, 6))
    low: Mapped[float | None] = mapped_column(Numeric(18, 6))
    close: Mapped[float | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[float | None] = mapped_column(Numeric(24, 4))
    vwap: Mapped[float | None] = mapped_column(Numeric(18, 6))
    trade_count: Mapped[int | None] = mapped_column(Integer)
    features: Mapped[dict | None] = mapped_column(JSONB)
    ingestion_latency_ms: Mapped[int | None] = mapped_column(Integer)
    ingestion_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )

    symbol_ref: Mapped["Symbol"] = relationship(back_populates="price_snapshots")


class CorporateAction(Base, TimestampMixin):
    __tablename__ = "corporate_actions"
    __table_args__ = (
        Index("ix_corporate_actions_symbol_effective", "symbol", "effective_date"),
        {"schema": "market"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(
        String(24), ForeignKey("market.symbols.symbol"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ratio: Mapped[float | None] = mapped_column(Numeric(18, 6))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_symbol_created_at", "symbol", "created_at"),
        {"schema": "trading"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    broker_order_id: Mapped[str | None] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(
        String(24), ForeignKey("market.symbols.symbol"), nullable=False
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    time_in_force: Mapped[str | None] = mapped_column(String(16))
    qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    filled_qty: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    limit_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    stop_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    fills: Mapped[list["Fill"]] = relationship(back_populates="order_ref", cascade="all, delete-orphan")


class Fill(Base, TimestampMixin):
    __tablename__ = "fills"
    __table_args__ = (
        Index("ix_fills_symbol_filled_at", "symbol", "filled_at"),
        {"schema": "trading"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trading.orders.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(
        String(24), ForeignKey("market.symbols.symbol"), nullable=False
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    fee: Mapped[float | None] = mapped_column(Numeric(18, 6))
    pnl: Mapped[float | None] = mapped_column(Numeric(18, 6))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    order_ref: Mapped["Order"] = relationship(back_populates="fills")


class Position(Base, TimestampMixin):
    __tablename__ = "positions"
    __table_args__ = (
        {"schema": "trading"},
    )

    symbol: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("market.symbols.symbol"),
        primary_key=True,
    )
    net_qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    avg_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    leverage: Mapped[float | None] = mapped_column(Numeric(10, 4))
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB)


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    __table_args__ = (
        {"schema": "trading"},
    )

    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    equity: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    cash: Mapped[float | None] = mapped_column(Numeric(20, 4))
    pnl_day: Mapped[float | None] = mapped_column(Numeric(20, 4))
    drawdown: Mapped[float | None] = mapped_column(Numeric(10, 4))
    leverage: Mapped[float | None] = mapped_column(Numeric(10, 4))
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB)


class RiskEvent(Base, TimestampMixin):
    __tablename__ = "risk_events"
    __table_args__ = (
        Index("ix_risk_events_symbol_triggered", "symbol", "triggered_at"),
        {"schema": "trading"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str | None] = mapped_column(String(24), ForeignKey("market.symbols.symbol"))
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    threshold: Mapped[float | None] = mapped_column(Numeric(18, 6))
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)


class StrategyRun(Base, TimestampMixin):
    __tablename__ = "strategy_runs"
    __table_args__ = (
        Index("ix_strategy_runs_strategy_started", "strategy_name", "started_at"),
        {"schema": "backtest"},
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_path: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    metrics_summary: Mapped[dict | None] = mapped_column(JSONB)

    equity_points: Mapped[list["StrategyRunEquity"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["StrategyRunMetric"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class StrategyRunMetric(Base):
    __tablename__ = "strategy_run_metrics"
    __table_args__ = (
        Index("ix_strategy_run_metrics_run_metric", "run_id", "metric_name"),
        {"schema": "backtest"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("backtest.strategy_runs.id"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB)

    run: Mapped["StrategyRun"] = relationship(back_populates="metrics")


class StrategyRunEquity(Base):
    __tablename__ = "strategy_run_equity"
    __table_args__ = (
        Index("ix_strategy_run_equity_run_ts", "run_id", "ts_utc"),
        {"schema": "backtest"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("backtest.strategy_runs.id"), nullable=False
    )
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    summary: Mapped[dict | None] = mapped_column("metadata", JSONB)

    run: Mapped["StrategyRun"] = relationship(back_populates="equity_points")


class DailyMetric(Base, TimestampMixin):
    __tablename__ = "daily_metrics"
    __table_args__ = (
        UniqueConstraint("metric_date", "metric_name", name="uq_daily_metrics_date_name"),
        {"schema": "analytics"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB)


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_owner_type", "owner_type", "owner_id"),
        {"schema": "storage"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(72))
    content_type: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    attributes: Mapped[dict | None] = mapped_column("metadata", JSONB)
