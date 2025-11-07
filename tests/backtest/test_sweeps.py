from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.backtest import sweeps


def test_expand_param_grid():
    grid = {"a": [1, 2], "b": ["x"]}
    combos = sweeps._expand_param_grid(grid)
    assert combos == [{"a": 1, "b": "x"}, {"a": 2, "b": "x"}]


def test_run_sweep_uses_persisted_frames(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = {
        "symbol": "AAPL",
        "start": "2023-01-01",
        "end": "2023-01-05",
        "strategy": "momentum",
        "use_probabilistic": True,
        "dal": {"vendor": "yahoo", "interval": "1Day"},
        "risk_agent": {"name": "fractional_kelly", "fraction": 0.4},
        "output_dir": str(tmp_path / "sweeps"),
        "params": {"roc_lookback": [2], "ema_fast": [3, 5]},
        "max_workers": 2,
    }
    cfg_path = tmp_path / "sweep.yml"
    cfg_path.write_text(yaml.safe_dump(cfg))

    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        job_dir = Path(kwargs["output_dir"])
        (job_dir / "artifact.txt").write_text("ok")
        return {
            "metrics": {"sharpe": 1.23},
            "equity_path": str(job_dir / "backtest_AAPL.csv"),
            "prob_frame_path": str(job_dir / "frame.parquet"),
        }

    monkeypatch.setattr(sweeps, "_run_backtest_core", fake_run)

    result = sweeps.run_sweep(cfg_path)

    assert len(result["results"]) == 2
    summary_path = Path(result["summary_path"])
    assert summary_path.exists()
    lines = summary_path.read_text().strip().splitlines()
    assert len(lines) == 2
    saved = [json.loads(line) for line in lines]
    assert {rec["params"]["ema_fast"] for rec in saved} == {3, 5}
    assert all(Path(rec["output_dir"]).exists() for rec in saved)
    assert len(calls) == 2
