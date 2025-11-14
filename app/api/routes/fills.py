from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.adapters.db.postgres import get_session
from app.db.repositories.trading import TradingRepository

router = APIRouter(prefix="/fills", tags=["fills"])


class FillRecord(BaseModel):
    id: int
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    filled_at: datetime
    pnl: Optional[float] = None
    fee: Optional[float] = None


@router.get("/", response_model=List[FillRecord])
def list_fills(
    limit: int = Query(100, ge=1, le=500), symbol: Optional[str] = None
) -> List[FillRecord]:
    with get_session() as session:
        repo = TradingRepository(session)
        symbols = [symbol] if symbol else None
        fills = repo.recent_trades(symbols=symbols, limit=limit)
        data = [
            {
                "id": fill.id,
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side,
                "qty": float(fill.qty),
                "price": float(fill.price),
                "filled_at": fill.filled_at,
                "pnl": float(fill.pnl) if fill.pnl is not None else None,
                "fee": float(fill.fee) if fill.fee is not None else None,
            }
            for fill in fills
        ]
    return [FillRecord(**row) for row in data]
