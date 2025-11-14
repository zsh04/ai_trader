from __future__ import annotations

import argparse
import itertools
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from time import perf_counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml
from loguru import logger

from app.backtest.run_breakout import _run_backtest_core
from app.backtest import sweep_registry
from app.eventbus.publisher import publish_event
from app.telemetry.backtest import record_run, start_span
from app.backtest import sweep_registry


def _load_config(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Sweep config must be a mapping")
    return data


def _expand_param_grid(grid: Dict[str, Iterable[Any]]) -> List[Dict[str, Any]]:
    if not grid:
        return [{}]
    keys = list(grid.keys())
    combos = []
    for values in itertools.product(*(grid[k] for k in keys)):
        combos.append(dict(zip(keys, values, strict=True)))
    return combos


def _prepare_base_kwargs(cfg: Dict[str, Any]) -> Dict[str, Any]:
    dal_cfg = cfg.get("dal", {}) or {}
    risk_cfg = cfg.get("risk_agent", {}) or {}
    return {
        "symbol": cfg["symbol"],
        "start": cfg["start"],
        "end": cfg.get("end"),
        "strategy": cfg.get("strategy", "breakout"),
        "slippage_bps": cfg.get("slippage_bps"),
        "fee_per_share": cfg.get("fee_per_share"),
        "risk_frac_override": cfg.get("risk_frac"),
        "min_notional": cfg.get("min_notional", 100.0),
        "debug": False,
        "debug_signals": False,
        "debug_entries": False,
        "regime_aware_sizing": cfg.get("regime_aware_sizing", False),
        "use_probabilistic": cfg.get("use_probabilistic", True),
        "dal_vendor": dal_cfg.get("vendor", "alpaca"),
        "dal_interval": dal_cfg.get("interval", "1Day"),
        "risk_agent": risk_cfg.get("name", "none"),
        "risk_agent_fraction": risk_cfg.get("fraction", 0.5),
    }


def _execute_job(
    job_idx: int,
    base_kwargs: Dict[str, Any],
    params: Dict[str, Any],
    sweep_dir: Path,
) -> Dict[str, Any]:
    job_dir = sweep_dir / f"job_{job_idx:04d}"
    job_dir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(base_kwargs)
    kwargs.update(
        {
            "params_kwargs": params,
            "export_csv": str(job_dir),
            "output_dir": str(job_dir),
            "no_save": False,
        }
    )
    attributes = {
        "strategy": base_kwargs.get("strategy", "breakout"),
        "risk_agent": base_kwargs.get("risk_agent", "none"),
        "dal_vendor": base_kwargs.get("dal_vendor"),
        "dal_interval": base_kwargs.get("dal_interval"),
        "use_probabilistic": str(
            bool(base_kwargs.get("use_probabilistic", True))
        ).lower(),
        "job_id": str(job_idx),
    }
    with start_span(attributes):
        result = _run_backtest_core(**kwargs)
    record_run(attributes)
    try:
        publish_event(
            "EH_HUB_JOBS",
            {
                "job_id": job_idx,
                "strategy": base_kwargs.get("strategy"),
                "risk_agent": base_kwargs.get("risk_agent"),
                "dal_vendor": base_kwargs.get("dal_vendor"),
                "dal_interval": base_kwargs.get("dal_interval"),
                "metrics": result.get("metrics", {}),
                "params": params,
            },
        )
    except Exception:
        logger.debug("[sweep] failed to emit job event job_id=%s", job_idx)
    payload = {
        "job_id": job_idx,
        "params": params,
        "metrics": result.get("metrics", {}),
        "equity_path": result.get("equity_path"),
        "prob_frame_path": result.get("prob_frame_path"),
        "output_dir": str(job_dir),
    }
    (job_dir / "summary.json").write_text(json.dumps(payload, default=str, indent=2))
    logger.info(
        "[sweep] job=%s strategy=%s params=%s sharpe=%s",
        job_idx,
        base_kwargs.get("strategy"),
        params,
        payload["metrics"].get("sharpe"),
    )
    return payload


def run_sweep(
    config_path: Path,
    *,
    job_id: str | None = None,
    mode: str = "local",
) -> Dict[str, Any]:
    cfg = _load_config(config_path)
    base_kwargs = _prepare_base_kwargs(cfg)
    param_grid = cfg.get("params", {}) or {}
    combos = _expand_param_grid(param_grid)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_output = Path(
        cfg.get("output_dir") or f"artifacts/backtests/{base_kwargs['strategy']}"
    )
    sweep_dir = base_output / timestamp
    sweep_dir.mkdir(parents=True, exist_ok=True)
    job_ref = job_id or timestamp
    sweep_registry.record_job_event(
        job_ref,
        "running",
        strategy=base_kwargs.get("strategy"),
        symbol=base_kwargs.get("symbol"),
        config_path=str(config_path),
        mode=mode,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    logger.info(
        "[sweep] starting job=%s dir=%s jobs=%s", job_ref, sweep_dir, len(combos)
    )
    started = perf_counter()
    results: List[Dict[str, Any]] = []
    max_workers = int(cfg.get("max_workers", min(4, len(combos) or 1))) or 1
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_execute_job, idx, base_kwargs, params, sweep_dir): (
                    idx,
                    params,
                )
                for idx, params in enumerate(combos, start=1)
            }
            for future in as_completed(future_map):
                job_idx, params = future_map[future]
                try:
                    payload = future.result()
                except Exception as exc:
                    logger.exception("[sweep] job=%s failed: %s", job_idx, exc)
                    continue
                results.append(payload)
    except Exception:
        sweep_registry.record_job_event(
            job_ref,
            "failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        raise
    summary_path = sweep_dir / "summary.jsonl"
    with summary_path.open("w") as handle:
        for record in results:
            handle.write(json.dumps(record, default=str) + "\n")
    duration_ms = (perf_counter() - started) * 1000.0
    sweep_registry.record_job_event(
        job_ref,
        "completed",
        sweep_dir=str(sweep_dir),
        summary_path=str(summary_path),
        results_count=len(results),
        finished_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )
    logger.info(
        "[sweep] completed job=%s dir=%s succeeded=%s", job_ref, sweep_dir, len(results)
    )
    return {
        "job_id": job_ref,
        "sweep_dir": str(sweep_dir),
        "summary_path": str(summary_path),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parameter sweeps for backtests")
    parser.add_argument("--config", required=True, help="Path to YAML sweep definition")
    args = parser.parse_args()
    run_sweep(Path(args.config))


if __name__ == "__main__":
    main()
