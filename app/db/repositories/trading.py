from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import models


class TradingRepository:
    """Persistence helpers for live trading data."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # Orders ------------------------------------------------------------------
    def upsert_orders(self, orders: Sequence[Mapping[str, object]]) -> None:
        if not orders:
            return
        stmt = insert(models.Order).values(orders)
        update_cols = {
            "broker_order_id": stmt.excluded.broker_order_id,
            "side": stmt.excluded.side,
            "order_type": stmt.excluded.order_type,
            "time_in_force": stmt.excluded.time_in_force,
            "qty": stmt.excluded.qty,
            "filled_qty": stmt.excluded.filled_qty,
            "limit_price": stmt.excluded.limit_price,
            "stop_price": stmt.excluded.stop_price,
            "status": stmt.excluded.status,
            "submitted_at": stmt.excluded.submitted_at,
            "raw_payload": stmt.excluded.raw_payload,
            "updated_at": stmt.excluded.updated_at,
        }
        self.session.execute(
            stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
        )

    def record_fills(self, fills: Sequence[Mapping[str, object]]) -> None:
        if not fills:
            return
        stmt = insert(models.Fill).values(fills)
        self.session.execute(stmt)

    def update_positions(self, positions: Sequence[Mapping[str, object]]) -> None:
        if not positions:
            return
        stmt = insert(models.Position).values(positions)
        update_cols = {
            "net_qty": stmt.excluded.net_qty,
            "avg_price": stmt.excluded.avg_price,
            "realized_pnl": stmt.excluded.realized_pnl,
            "unrealized_pnl": stmt.excluded.unrealized_pnl,
            "leverage": stmt.excluded.leverage,
            "extra": stmt.excluded.extra,
            "updated_at": stmt.excluded.updated_at,
        }
        self.session.execute(
            stmt.on_conflict_do_update(index_elements=["symbol"], set_=update_cols)
        )

    def record_equity_snapshot(self, snapshot: Mapping[str, object]) -> None:
        stmt = insert(models.EquitySnapshot).values(snapshot)
        self.session.execute(stmt.on_conflict_do_nothing(index_elements=["ts_utc"]))

    def record_risk_events(self, events: Sequence[Mapping[str, object]]) -> None:
        if not events:
            return
        stmt = insert(models.RiskEvent).values(events)
        self.session.execute(stmt)

    # Queries -----------------------------------------------------------------
    def recent_equity(
        self, *, since: datetime | None = None, limit: int = 390
    ) -> list[models.EquitySnapshot]:
        stmt = (
            select(models.EquitySnapshot)
            .order_by(models.EquitySnapshot.ts_utc.desc())
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(models.EquitySnapshot.ts_utc >= since)
        snapshots = list(self.session.scalars(stmt))
        snapshots.reverse()
        return snapshots

    def recent_trades(
        self, symbols: Iterable[str] | None = None, limit: int = 150
    ) -> list[models.Fill]:
        stmt = select(models.Fill).order_by(models.Fill.filled_at.desc()).limit(limit)
        if symbols:
            sym_list = list({sym.upper() for sym in symbols if sym})
            if sym_list:
                stmt = stmt.where(models.Fill.symbol.in_(sym_list))
        return list(self.session.scalars(stmt))

    def recent_orders(self, *, limit: int = 50) -> list[models.Order]:
        stmt = (
            select(models.Order).order_by(models.Order.created_at.desc()).limit(limit)
        )
        return list(self.session.scalars(stmt))

    def all_positions(self) -> list[models.Position]:
        stmt = select(models.Position).order_by(models.Position.symbol.asc())
        return list(self.session.scalars(stmt))
