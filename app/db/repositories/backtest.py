from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import models


class BacktestRepository:
    """Persist and retrieve backtest strategy metadata."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self, payload: Mapping[str, object]) -> models.StrategyRun:
        run = models.StrategyRun(**payload)
        self.session.add(run)
        return run

    def update_run_status(
        self,
        run_id: str,
        *,
        status: str,
        completed_at: datetime | None = None,
        metrics_summary: dict | None = None,
    ) -> None:
        stmt = (
            select(models.StrategyRun)
            .where(models.StrategyRun.id == run_id)
            .with_for_update()
        )
        run = self.session.scalar(stmt)
        if run is None:
            raise ValueError(f"StrategyRun {run_id} not found")
        run.status = status
        run.completed_at = completed_at
        if metrics_summary is not None:
            run.metrics_summary = metrics_summary

    def record_equity(self, run_id: str, points: Sequence[Mapping[str, object]]) -> None:
        if not points:
            return
        normalized = []
        for point in points:
            data = dict(point)
            data.setdefault("run_id", run_id)
            normalized.append(data)
        stmt = insert(models.StrategyRunEquity).values(normalized)
        self.session.execute(stmt)

    def record_metrics(self, run_id: str, metrics: Sequence[Mapping[str, object]]) -> None:
        if not metrics:
            return
        normalized = []
        for metric in metrics:
            data = dict(metric)
            data.setdefault("run_id", run_id)
            normalized.append(data)
        stmt = insert(models.StrategyRunMetric).values(normalized)
        self.session.execute(stmt)

    def fetch_run(self, run_id: str) -> models.StrategyRun | None:
        stmt = select(models.StrategyRun).where(models.StrategyRun.id == run_id)
        return self.session.scalar(stmt)

    def recent_runs(self, *, strategy_name: str | None = None, limit: int = 20) -> list[models.StrategyRun]:
        stmt = select(models.StrategyRun).order_by(models.StrategyRun.created_at.desc()).limit(limit)
        if strategy_name:
            stmt = stmt.where(models.StrategyRun.strategy_name == strategy_name)
        return list(self.session.scalars(stmt))
