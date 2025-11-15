from __future__ import annotations

from typing import Any, Dict

from ui.services.api_routes import ROUTES
from ui.services.http_client import HttpClient


class OrdersService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def list_orders(self, params: Dict[str, str] | None = None) -> Any:
        return self.client.request("GET", ROUTES.orders, params=params, ui_action="orders.list")

    def list_fills(self, params: Dict[str, str] | None = None) -> Any:
        return self.client.request("GET", ROUTES.fills, params=params, ui_action="fills.list")
