from __future__ import annotations

from dataclasses import dataclass

from ui.services.backtests import BacktestService
from ui.services.health import HealthService
from ui.services.http_client import HttpClient
from ui.services.models import ModelsService
from ui.services.orders import OrdersService
from ui.services.trading import TradingService
from ui.services.watchlists import WatchlistService
from ui.settings.config import AppSettings


@dataclass
class ServicesRegistry:
    client: HttpClient
    models: ModelsService
    backtests: BacktestService
    orders: OrdersService
    trading: TradingService
    watchlists: WatchlistService
    health: HealthService


def build_services(settings: AppSettings) -> ServicesRegistry:
    client = HttpClient(settings)
    return ServicesRegistry(
        client=client,
        models=ModelsService(client),
        backtests=BacktestService(client),
        orders=OrdersService(client),
        trading=TradingService(client),
        watchlists=WatchlistService(client),
        health=HealthService(client),
    )
