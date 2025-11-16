from __future__ import annotations

from typing import Any, Dict

from ui.services.api_routes import ROUTES
from ui.services.http_client import HttpClient


class BacktestService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def list_jobs(self, params: Dict[str, str] | None = None) -> Any:
        return self.client.request(
            "GET", ROUTES.sweeps_jobs, params=params, ui_action="backtests.list"
        )

    def submit_job(
        self, payload: Dict[str, Any], *, request_id: str | None = None
    ) -> Any:
        return self.client.request(
            "POST",
            ROUTES.sweeps_jobs,
            json=payload,
            ui_action="backtests.submit",
            request_id=request_id,
        )

    def job_detail(self, job_id: str) -> Any:
        path = ROUTES.sweeps_job_detail.format(job_id=job_id)
        return self.client.request("GET", path, ui_action="backtests.detail")

    def sweep_status(self, job_id: str) -> Any:
        path = ROUTES.sweep_run_status.format(job_id=job_id)
        return self.client.request("GET", path, ui_action="backtests.results")
