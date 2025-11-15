from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiRoutes:
    health_live: str = "/health/live"
    health_ready: str = "/health/ready"
    openapi: str = "/openapi.json"
    models: str = "/models"
    model_warm: str = "/models/{service}/warm"
    model_sync: str = "/models/{service}/adapters/sync"
    model_shadow: str = "/models/{service}/shadow"
    sweeps_jobs: str = "/backtests/sweeps/jobs"
    sweeps_job_detail: str = "/backtests/sweeps/jobs/{job_id}"
    orders: str = "/orders"
    fills: str = "/fills"
    trades: str = "/trades/{symbol}"
    positions: str = "/positions"
    equity: str = "/equity/{account}"
    signals: str = "/signals/{symbol}"
    watchlists: str = "/watchlists"


ROUTES = ApiRoutes()
