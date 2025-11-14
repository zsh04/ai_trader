from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

MANIFEST_ROOT = Path("artifacts/backtests/sweeps")
MANIFEST_PATH = MANIFEST_ROOT / "jobs_manifest.jsonl"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_manifest_dir() -> None:
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)


@dataclass
class SweepJobRecord:
    job_id: str
    status: str
    strategy: Optional[str] = None
    config_path: Optional[str] = None
    symbol: Optional[str] = None
    mode: Optional[str] = "local"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[float] = None
    sweep_dir: Optional[str] = None
    summary_path: Optional[str] = None
    results_count: Optional[int] = None


def _append_record(record: Dict[str, object]) -> None:
    _ensure_manifest_dir()
    with MANIFEST_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def record_job_event(job_id: str, status: str, **payload: object) -> None:
    data = {
        "job_id": job_id,
        "status": status,
        "ts": _utcnow().isoformat(),
    }
    data.update(payload)
    _append_record(data)


def load_jobs(limit: int = 50) -> List[Dict[str, object]]:
    if not MANIFEST_PATH.exists():
        return []
    records: List[Dict[str, object]] = []
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError:
                continue
    records.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return records[:limit]


__all__ = ["record_job_event", "load_jobs", "MANIFEST_PATH"]
