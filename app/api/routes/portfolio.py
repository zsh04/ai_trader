from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.adapters.db.postgres import get_session
from app.db.repositories.trading import TradingRepository

router = APIRouter(tags=["trading"])


def _as_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:  # pragma: no cover - defensive
        return None


class PositionRecord(BaseModel):
    symbol: str
    net_qty: float
    avg_price: float
    realized_pnl: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    leverage: Optional[float] = None
    extra: Optional[dict] = None
    updated_at: Optional[datetime] = None


class EquityPoint(BaseModel):
    ts: datetime
    equity: float
    cash: Optional[float] = None
    pnl_day: Optional[float] = None
    drawdown: Optional[float] = None
    leverage: Optional[float] = None


class EquitySeries(BaseModel):
    account: str
    points: list[EquityPoint]


class TradeRecord(BaseModel):
    id: int
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    fee: Optional[float] = None
    pnl: Optional[float] = None
    filled_at: datetime


@router.get("/positions", response_model=list[PositionRecord])
def list_positions() -> list[PositionRecord]:
    with get_session() as session:
        repo = TradingRepository(session)
        positions = repo.all_positions()
    return [
        PositionRecord(
            symbol=pos.symbol,
            net_qty=float(pos.net_qty),
            avg_price=float(pos.avg_price),
            realized_pnl=_as_float(pos.realized_pnl),
            unrealized_pnl=_as_float(pos.unrealized_pnl),
            leverage=_as_float(pos.leverage),
            extra=pos.extra,
            updated_at=pos.updated_at,
        )
        for pos in positions
    ]


@router.get("/equity/{account}", response_model=EquitySeries)
def equity_series(account: str, limit: int = Query(390, ge=1, le=1440)) -> EquitySeries:
    with get_session() as session:
        repo = TradingRepository(session)
        snapshots = repo.recent_equity(limit=limit)
    points = [
        EquityPoint(
            ts=snapshot.ts_utc,
            equity=float(snapshot.equity),
            cash=_as_float(snapshot.cash),
            pnl_day=_as_float(snapshot.pnl_day),
            drawdown=_as_float(snapshot.drawdown),
            leverage=_as_float(snapshot.leverage),
        )
        for snapshot in snapshots
    ]
    return EquitySeries(account=account, points=points)


@router.get("/trades/{symbol}", response_model=list[TradeRecord])
def list_trades(
    symbol: str,
    limit: int = Query(150, ge=1, le=500),
) -> list[TradeRecord]:
    symbols = None
    normalized = symbol.strip()
    if normalized and normalized not in {"*", "all"}:
        symbols = [normalized]
    with get_session() as session:
        repo = TradingRepository(session)
        fills = repo.recent_trades(symbols=symbols, limit=limit)
    return [
        TradeRecord(
            id=fill.id,
            order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side,
            qty=float(fill.qty),
            price=float(fill.price),
            fee=_as_float(fill.fee),
            pnl=_as_float(fill.pnl),
            filled_at=fill.filled_at,
        )
        for fill in fills
    ]
