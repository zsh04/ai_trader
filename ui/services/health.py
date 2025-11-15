from __future__ import annotations

from typing import Any

from ui.services.api_routes import ROUTES
from ui.services.http_client import HttpClient


class HealthService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def live(self) -> Any:
        return self.client.request("GET", ROUTES.health_live, ui_action="health.live")

    def ready(self) -> Any:
        return self.client.request("GET", ROUTES.health_ready, ui_action="health.ready")

    def openapi(self) -> Any:
        return self.client.request("GET", ROUTES.openapi, ui_action="health.openapi")
