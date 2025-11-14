from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.routes import backtest as backtest_module

client = TestClient(main_module.app)


def test_list_sweep_jobs(monkeypatch):
    monkeypatch.setattr(
        backtest_module.sweep_registry,
        "load_jobs",
        lambda limit: [
            {
                "job_id": "job-1",
                "status": "completed",
                "strategy": "breakout",
                "results_count": 10,
            }
        ],
    )
    resp = client.get("/backtests/sweeps/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["job_id"] == "job-1"
    assert data[0]["status"] == "completed"


def test_trigger_sweep_job(monkeypatch):
    events = {}

    def _fake_publish(key, payload):
        events[key] = payload

    monkeypatch.setattr(backtest_module, "publish_event", _fake_publish)
    resp = client.post(
        "/backtests/sweeps/jobs",
        json={"config_path": "blob://configs/momentum.yaml", "strategy": "momentum"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert "EH_HUB_JOBS" in events
