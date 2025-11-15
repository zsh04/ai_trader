from __future__ import annotations

from typing import Any, Dict

from ui.services.api_routes import ROUTES
from ui.services.http_client import HttpClient


class WatchlistService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def list_watchlists(self) -> Any:
        return self.client.request("GET", ROUTES.watchlists, ui_action="watchlists.list")

    def save_watchlist(self, payload: Dict[str, Any], *, request_id: str | None = None) -> Any:
        return self.client.request(
            "POST",
            ROUTES.watchlists,
            json=payload,
            ui_action="watchlists.save",
            request_id=request_id,
        )

    def signals(self, symbol: str) -> Any:
        path = ROUTES.signals.format(symbol=symbol)
        return self.client.request("GET", path, ui_action="signals.fetch")
