from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from models.common.logging import configure_logging, instrument_fastapi, request_context

from .health import build_health_router
from .runtime import FinbertRuntime

configure_logging()
app = FastAPI(title="AI Trader NLP", version="1.0.0")
runtime = FinbertRuntime()
instrument_fastapi(app)
app.include_router(build_health_router(runtime))


class SentimentRequest(BaseModel):
    text: str


class SentimentResponse(BaseModel):
    label: str
    score: float
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
        logger.exception("[finbert] request errored", request_id=ctx["request_id"])
        raise
    response.headers["X-Request-Id"] = ctx["request_id"]
    return response


@app.post("/classify-sentiment", response_model=SentimentResponse)
async def classify(payload: SentimentRequest) -> SentimentResponse:
    if not runtime.ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "runtime not ready"},
        )
    result = runtime.classify(payload.text)
    return SentimentResponse(**result)
