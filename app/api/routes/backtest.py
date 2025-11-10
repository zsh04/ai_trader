from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.backtest import sweeps
from app.backtest.run_breakout import run as run_backtest

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


class SweepStatus(BaseModel):
    job_id: str
    sweep_dir: str
    summary_path: str
    results: List[Dict[str, Any]]


_sweep_jobs: Dict[str, SweepStatus] = {}


def _kickoff_sweep(job_id: str, config: SweepRequest) -> None:
    if config.config_path:
        result = sweeps.run_sweep(Path(config.config_path))
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
        result = sweeps.run_sweep(temp_path)
    _sweep_jobs[job_id] = SweepStatus(job_id=job_id, **result)


@router.post("/sweeps", response_model=SweepStatus)
def start_sweep(req: SweepRequest, background: BackgroundTasks) -> SweepStatus:
    job_id = f"sweep-{len(_sweep_jobs) + 1}"
    background.add_task(_executor.submit, _kickoff_sweep, job_id, req)
    return SweepStatus(job_id=job_id, sweep_dir="PENDING", summary_path="", results=[])


@router.get("/sweeps/{job_id}", response_model=SweepStatus)
def get_sweep(job_id: str) -> SweepStatus:
    status = _sweep_jobs.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="sweep not found")
    return status


class BacktestRequest(BaseModel):
    symbol: str
    start: str
    end: Optional[str] = None
    strategy: str = "breakout"
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/run")
def run_backtest_endpoint(req: BacktestRequest) -> Dict[str, Any]:
    result = run_backtest(
        symbol=req.symbol,
        start=req.start,
        end=req.end,
        params_kwargs=req.params,
        strategy=req.strategy,
    )
    return result
