from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.adapters.db.postgres import get_session
from app.db.repositories.trading import TradingRepository

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderRecord(BaseModel):
    id: str
    symbol: str
    side: str
    qty: float
    status: str
    submitted_at: Optional[datetime]
    strategy: Optional[str] = None
    run_id: Optional[str] = None
    broker_order_id: Optional[str] = None


def _list_recent_orders(limit: int) -> List[dict]:
    with get_session() as session:
        repo = TradingRepository(session)
        orders = repo.recent_orders(limit=limit)
        data: List[dict] = []
        for order in orders:
            payload = getattr(order, "raw_payload", {}) or {}
            data.append(
                {
                    "id": order.id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": float(order.qty),
                    "status": order.status,
                    "submitted_at": order.submitted_at,
                    "strategy": payload.get("strategy"),
                    "run_id": payload.get("run_id", payload.get("run")),
                    "broker_order_id": order.broker_order_id,
                }
            )
        return data


@router.get("/", response_model=List[OrderRecord])
def list_orders(limit: int = Query(50, ge=1, le=500)) -> List[OrderRecord]:
    records = _list_recent_orders(limit)
    return [OrderRecord(**record) for record in records]
