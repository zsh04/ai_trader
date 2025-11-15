from __future__ import annotations

from typing import Any

from ui.services.api_routes import ROUTES
from ui.services.http_client import HttpClient


class TradingService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def list_positions(self) -> Any:
        return self.client.request("GET", ROUTES.positions, ui_action="positions.list")

    def equity_curve(self, account: str) -> Any:
        path = ROUTES.equity.format(account=account)
        return self.client.request("GET", path, ui_action="equity.fetch")

    def trades(self, symbol: str) -> Any:
        path = ROUTES.trades.format(symbol=symbol)
        return self.client.request("GET", path, ui_action="trades.list")
