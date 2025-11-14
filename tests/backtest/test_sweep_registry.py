from __future__ import annotations

from app.backtest import sweep_registry


def test_record_and_load_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_registry, "MANIFEST_ROOT", tmp_path)
    monkeypatch.setattr(
        sweep_registry,
        "MANIFEST_PATH",
        tmp_path / "jobs_manifest.jsonl",
    )
    sweep_registry.record_job_event("job-1", "queued", strategy="breakout")
    sweep_registry.record_job_event("job-1", "completed", results_count=5)
    jobs = sweep_registry.load_jobs()
    assert len(jobs) == 2
    assert jobs[0]["status"] == "completed"
    assert jobs[1]["status"] == "queued"
