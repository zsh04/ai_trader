from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from models.common.logging import configure_logging, instrument_fastapi, request_context

from .health import build_health_router
from .runtime import ChronosRuntime

configure_logging()
app = FastAPI(title="AI Trader Forecast", version="1.0.0")
runtime = ChronosRuntime()
instrument_fastapi(app)
app.include_router(build_health_router(runtime))


class ForecastRequest(BaseModel):
    series: list[float] = Field(..., min_length=1)
    horizon: int = Field(..., gt=0)
    freq: str | None = None


class ForecastResponse(BaseModel):
    forecast: list[float]
    adapter_tag: str
    hf_sha: str


@app.on_event("startup")
async def startup() -> None:
    runtime.load()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    ctx = request_context(request)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("[chronos2] request failure", request_id=ctx["request_id"])
        raise
    response.headers["X-Request-Id"] = ctx["request_id"]
    return response


@app.post("/forecast", response_model=ForecastResponse)
async def forecast(payload: ForecastRequest):
    if not runtime.ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "runtime not ready"},
        )
    result = runtime.forecast(payload.series, payload.horizon)
    return ForecastResponse(**result)
