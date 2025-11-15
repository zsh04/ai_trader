from __future__ import annotations

from typing import Any

from ui.services.api_routes import ROUTES
from ui.services.http_client import HttpClient


class ModelsService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def list_models(self) -> Any:
        return self.client.request("GET", ROUTES.models, ui_action="models.list")

    def warm(self, service: str, *, request_id: str | None = None) -> Any:
        path = ROUTES.model_warm.format(service=service)
        return self.client.request(
            "POST", path, ui_action="models.warm", request_id=request_id
        )

    def sync_adapter(self, service: str, *, request_id: str | None = None) -> Any:
        path = ROUTES.model_sync.format(service=service)
        return self.client.request(
            "POST", path, ui_action="models.sync", request_id=request_id
        )

    def toggle_shadow(self, service: str, *, request_id: str | None = None) -> Any:
        path = ROUTES.model_shadow.format(service=service)
        return self.client.request(
            "POST", path, ui_action="models.shadow", request_id=request_id
        )
