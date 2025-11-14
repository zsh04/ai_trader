from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.backtest import sweeps, sweep_registry
from app.backtest.run_breakout import run as run_backtest
from app.eventbus.publisher import publish_event

router = APIRouter(prefix="/backtests", tags=["backtests"])

_executor = ThreadPoolExecutor(max_workers=4)


class SweepRequest(BaseModel):
    config_path: Optional[str] = Field(
        default=None,
        description="Path to a YAML sweep config. Optional if inline params provided.",
    )
    symbol: Optional[str] = None
    strategy: Optional[str] = None
    params: Dict[str, List[Any]] = Field(
        default_factory=dict,
        description="Override/inline grid parameters when config_path is omitted.",
    )
    output_dir: Optional[str] = None
    mode: Optional[str] = Field(
        default="local", description="Execution mode (local|aca)"
    )


class SweepStatus(BaseModel):
    job_id: str
    sweep_dir: str
    summary_path: str
    results: List[Dict[str, Any]]


_sweep_jobs: Dict[str, SweepStatus] = {}


def _kickoff_sweep(job_id: str, config: SweepRequest) -> None:
    mode = (config.mode or "local").lower()
    sweep_registry.record_job_event(
        job_id,
        "queued",
        strategy=config.strategy,
        symbol=config.symbol,
        config_path=config.config_path,
        mode=mode,
    )
    try:
        if config.config_path:
            result = sweeps.run_sweep(
                Path(config.config_path), job_id=job_id, mode=mode
            )
        else:
            cfg = {
                "symbol": config.symbol or "AAPL",
                "strategy": config.strategy or "breakout",
                "params": config.params,
                "output_dir": config.output_dir,
            }
            temp_path = Path("artifacts/backtests/sweeps/temp_config.json")
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(json.dumps(cfg))
            result = sweeps.run_sweep(temp_path, job_id=job_id, mode=mode)
        _sweep_jobs[job_id] = SweepStatus(job_id=job_id, **result)
    except Exception as exc:
        sweep_registry.record_job_event(
            job_id,
            "failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )
        raise


@router.post("/sweeps", response_model=SweepStatus)
def start_sweep(req: SweepRequest, background: BackgroundTasks) -> SweepStatus:
    job_id = f"sweep-{len(_sweep_jobs) + 1}"
    background.add_task(_executor.submit, _kickoff_sweep, job_id, req)
    return SweepStatus(job_id=job_id, sweep_dir="PENDING", summary_path="", results=[])


class BacktestRequest(BaseModel):
    symbol: str
    start: str
    end: Optional[str] = None
    strategy: str = "breakout"
    params: Dict[str, Any] = Field(default_factory=dict)
    use_probabilistic: bool = False
    dal_vendor: str = "alpaca"
    dal_interval: str = "1Day"
    regime_aware_sizing: bool = False
    risk_agent: str = "none"
    risk_agent_fraction: float = 0.5
    slippage_bps: Optional[float] = None
    fee_per_share: Optional[float] = None
    risk_frac: Optional[float] = None
    min_notional: float = 100.0


class SweepJobRecord(BaseModel):
    job_id: str
    status: str
    ts: Optional[str] = None
    strategy: Optional[str] = None
    symbol: Optional[str] = None
    sweep_dir: Optional[str] = None
    results_count: Optional[int] = None
    duration_ms: Optional[float] = None


@router.get("/sweeps/jobs", response_model=List[SweepJobRecord])
def list_sweep_jobs(limit: int = 50) -> List[SweepJobRecord]:
    jobs = sweep_registry.load_jobs(limit)
    return [SweepJobRecord(**job) for job in jobs]


@router.get("/sweeps/jobs/{job_id}", response_model=List[SweepJobRecord])
def get_sweep_job(job_id: str) -> List[SweepJobRecord]:
    jobs = [
        job
        for job in sweep_registry.load_jobs(limit=200)
        if job.get("job_id") == job_id
    ]
    if not jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return [SweepJobRecord(**job) for job in jobs]


class SweepJobTriggerRequest(BaseModel):
    config_path: str = Field(..., description="Path or blob URI to the sweep config")
    strategy: Optional[str] = None
    symbol: Optional[str] = None
    mode: str = Field(default="aca")
    job_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.post("/sweeps/jobs", response_model=SweepJobRecord)
def trigger_sweep_job(req: SweepJobTriggerRequest) -> SweepJobRecord:
    job_id = req.job_id or f"sweep-{uuid4().hex[:8]}"
    event_payload = {
        "job_id": job_id,
        "config_path": req.config_path,
        "strategy": req.strategy,
        "symbol": req.symbol,
        "mode": req.mode,
        "metadata": req.metadata,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        publish_event("EH_HUB_JOBS", event_payload)
    except Exception as exc:  # pragma: no cover - Event Hub optional
        raise HTTPException(status_code=500, detail=f"failed to enqueue job: {exc}")
    sweep_registry.record_job_event(
        job_id,
        "queued",
        strategy=req.strategy,
        symbol=req.symbol,
        config_path=req.config_path,
        mode=req.mode,
        metadata=req.metadata,
    )
    return SweepJobRecord(job_id=job_id, status="queued", strategy=req.strategy, symbol=req.symbol)


@router.get("/sweeps/{job_id}", response_model=SweepStatus)
def get_sweep(job_id: str) -> SweepStatus:
    status = _sweep_jobs.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="sweep not found")
    return status


@router.post("/run")
def run_backtest_endpoint(req: BacktestRequest) -> Dict[str, Any]:
    result = run_backtest(
        symbol=req.symbol,
        start=req.start,
        end=req.end,
        params_kwargs=req.params,
        strategy=req.strategy,
        use_probabilistic=req.use_probabilistic,
        dal_vendor=req.dal_vendor,
        dal_interval=req.dal_interval,
        regime_aware_sizing=req.regime_aware_sizing,
        risk_agent=req.risk_agent,
        risk_agent_fraction=req.risk_agent_fraction,
        slippage_bps=req.slippage_bps,
        fee_per_share=req.fee_per_share,
        risk_frac_override=req.risk_frac,
        min_notional=req.min_notional,
    )
    return result
