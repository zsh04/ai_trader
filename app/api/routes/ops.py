from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.dal.manager import MarketDataDAL
from app.eventbus.publisher import publish_event
from app.probability.storage import build_frame_path

router = APIRouter(prefix="/ops", tags=["ops"])


class SmokeStatus(BaseModel):
    vendor: str
    success: bool
    bars: int = Field(0, description="Number of bars returned")
    message: Optional[str] = None


class DalSmokeResponse(BaseModel):
    timestamp: datetime
    symbol: str
    alpha_vantage: SmokeStatus
    finnhub: SmokeStatus


class ProbFrameResponse(BaseModel):
    symbol: str
    strategy: str
    vendor: str
    interval: str
    rows: int
    columns: list[str]
    preview: list[Dict[str, Any]]


class EventHubTestRequest(BaseModel):
    hub_env_key: str = Field(..., description="Env var name pointing to the Event Hub")
    payload: Dict[str, Any]


def _run_smoke(symbol: str) -> DalSmokeResponse:
    dal = MarketDataDAL(enable_postgres_metadata=False)
    now = datetime.now(timezone.utc)
    av_status = _fetch_status(
        dal,
        symbol,
        vendor="alphavantage",
        interval="5Min",
        start=now - timedelta(days=5),
        end=now,
    )
    fh_status = _fetch_status(
        dal,
        symbol,
        vendor="finnhub",
        interval="1Day",
        start=now - timedelta(days=30),
        end=now,
    )
    result = DalSmokeResponse(
        timestamp=now,
        symbol=symbol,
        alpha_vantage=av_status,
        finnhub=fh_status,
    )
    payload = {
        "type": "dal_smoke",
        "timestamp": result.timestamp.isoformat(),
        "symbol": symbol,
        "alpha_vantage": av_status.dict(),
        "finnhub": fh_status.dict(),
    }
    try:
        publish_event("EH_HUB_SIGNALS", payload)
    except Exception as exc:  # pragma: no cover - telemetry best effort
        logging.getLogger(__name__).debug("DAL smoke telemetry publish failed: %s", exc)
    return result


def _fetch_status(
    dal: MarketDataDAL,
    symbol: str,
    *,
    vendor: str,
    interval: str,
    start: datetime,
    end: Optional[datetime],
) -> SmokeStatus:
    try:
        batch = dal.fetch_bars(
            symbol,
            start=start,
            end=end,
            interval=interval,
            vendor=vendor,
        )
        bars = len(batch.bars.data)
        success = bars > 0
        message = None if success else "No bars returned"
        return SmokeStatus(vendor=vendor, success=success, bars=bars, message=message)
    except Exception as exc:  # pragma: no cover - network path
        return SmokeStatus(
            vendor=vendor,
            success=False,
            bars=0,
            message=str(exc),
        )


@router.post("/dal-smoke", response_model=DalSmokeResponse)
def run_dal_smoke(symbol: str = "AAPL") -> DalSmokeResponse:
    """Execute the DAL smoke test against Alpha Vantage + Finnhub."""

    result = _run_smoke(symbol.upper())
    if not (result.alpha_vantage.success or result.finnhub.success):
        raise HTTPException(status_code=503, detail="DAL smoke failed")
    return result


@router.get("/prob-frame", response_model=ProbFrameResponse)
def get_prob_frame(
    symbol: str,
    strategy: str,
    vendor: str,
    interval: str = "1Day",
    limit: int = 200,
) -> ProbFrameResponse:
    path = build_frame_path(symbol, strategy, vendor=vendor, interval=interval)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Frame not found")
    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover - IO path
        raise HTTPException(
            status_code=500, detail=f"Failed to load frame: {exc}"
        ) from exc
    preview_df = df.tail(limit)
    records = preview_df.reset_index().to_dict("records")
    return ProbFrameResponse(
        symbol=symbol,
        strategy=strategy,
        vendor=vendor,
        interval=interval,
        rows=len(df),
        columns=list(df.columns),
        preview=records,
    )


@router.post("/eventhub-test")
def send_eventhub_test(req: EventHubTestRequest) -> Dict[str, str]:
    try:
        publish_event(req.hub_env_key, req.payload)
    except Exception as exc:  # pragma: no cover - telemetry best effort
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "sent"}
