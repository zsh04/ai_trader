from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.orchestration.router import run_router
from app.orchestration.types import RouterContext, RouterRequest

router = APIRouter(prefix="/router", tags=["router"])


class RouterRunPayload(BaseModel):
    symbol: str = Field(..., description="Ticker symbol (e.g., AAPL)")
    start: datetime = Field(..., description="Start timestamp (ISO-8601)")
    end: Optional[datetime] = Field(
        None, description="End timestamp (default = now in UTC)"
    )
    strategy: str = Field(
        "breakout", description="breakout | momentum | mean_reversion"
    )
    params: Dict[str, Any] = Field(default_factory=dict)
    use_probabilistic: bool = True
    dal_vendor: str = "alpaca"
    dal_interval: str = "1Day"
    min_notional: float = 100.0
    max_notional: float = 5_000.0
    side: str = "buy"
    publish_orders: bool = False
    execute_orders: bool = False
    offline_mode: bool = False


class RouterRunResponse(BaseModel):
    run_id: str
    symbol: str
    strategy: str
    latency_ms: float
    order_intent: Optional[Dict[str, Any]]
    prob_frame_path: Optional[str]
    priors: Optional[Dict[str, Any]]
    events: list[str]
    errors: list[str]
    fallback_reason: Optional[str]


@router.post("/run", response_model=RouterRunResponse)
def run_router_endpoint(payload: RouterRunPayload) -> RouterRunResponse:
    request = RouterRequest(
        symbol=payload.symbol,
        start=payload.start,
        end=payload.end,
        strategy=payload.strategy,
        params=payload.params,
        use_probabilistic=payload.use_probabilistic,
        dal_vendor=payload.dal_vendor,
        dal_interval=payload.dal_interval,
        min_notional=payload.min_notional,
        max_notional=payload.max_notional,
        side=payload.side,
    )
    context = RouterContext(
        publish_orders=payload.publish_orders,
        execute_orders=payload.execute_orders,
        offline_mode=payload.offline_mode,
        alpaca_key=settings.alpaca_key if payload.execute_orders else None,
        alpaca_secret=settings.alpaca_secret if payload.execute_orders else None,
        alpaca_base_url=settings.alpaca_base_url,
    )
    if payload.execute_orders and (not context.alpaca_key or not context.alpaca_secret):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Alpaca credentials missing; cannot execute orders.",
        )
    result = run_router(request, context)
    return RouterRunResponse(**asdict(result))
