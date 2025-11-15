from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


def _sample_models() -> List[Dict[str, Any]]:
    return [
        {
            "service": "finbert",
            "name": "ai-trader-nlp",
            "adapter_tag": "base",
            "status": "ready",
            "warm": True,
            "shadow": False,
            "metadata": {"hf_repo": "ProsusAI/finbert"},
        },
        {
            "service": "chronos2",
            "name": "ai-trader-forecast",
            "adapter_tag": "base",
            "status": "ready",
            "warm": False,
            "shadow": True,
            "metadata": {"hf_repo": "amazon/chronos-2"},
        },
    ]


@dataclass
class MockModelsService:
    data: List[Dict[str, Any]] = field(default_factory=_sample_models)

    def list_models(self) -> List[Dict[str, Any]]:
        return list(self.data)

    def warm(self, service: str, *, request_id: str | None = None) -> Dict[str, Any]:
        return next(model for model in self.data if model["service"] == service)

    def sync_adapter(
        self, service: str, *, request_id: str | None = None
    ) -> Dict[str, Any]:
        return next(model for model in self.data if model["service"] == service)

    def toggle_shadow(
        self, service: str, *, request_id: str | None = None
    ) -> Dict[str, Any]:
        return next(model for model in self.data if model["service"] == service)


@dataclass
class MockBacktestService:
    def list_jobs(self, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        return [
            {"job_id": "mock-1", "status": "completed"},
            {"job_id": "mock-2", "status": "running"},
        ]

    def submit_job(
        self, payload: Dict[str, Any], *, request_id: str | None = None
    ) -> Dict[str, Any]:
        return {"job_id": "mock-submitted", "status": "queued", **payload}

    def job_detail(self, job_id: str) -> List[Dict[str, Any]]:
        return [{"job_id": job_id, "status": "completed"}]


@dataclass
class MockOrdersService:
    def list_orders(self, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        return [{"id": "ord-1", "symbol": "AAPL", "qty": 10, "status": "filled"}]

    def list_fills(self, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        return [
            {
                "order_id": "ord-1",
                "symbol": "AAPL",
                "qty": 10,
                "price": 190.0,
                "filled_at": "2025-01-02T00:00:00Z",
            }
        ]


@dataclass
class MockTradingService:
    def list_positions(self) -> List[Dict[str, Any]]:
        return [{"symbol": "AAPL", "qty": 20, "account": "primary"}]

    def equity_curve(self, account: str) -> Dict[str, Any]:
        return {"points": [{"timestamp": "2025-01-02T00:00:00Z", "equity": 100000}]}

    def trades(self, symbol: str) -> List[Dict[str, Any]]:
        return [
            {
                "symbol": symbol,
                "qty": 10,
                "price": 190.0,
                "timestamp": "2025-01-02T01:00:00Z",
            }
        ]


@dataclass
class MockWatchlistService:
    def list_watchlists(self) -> List[Dict[str, Any]]:
        return [
            {
                "bucket": "core",
                "name": "core",
                "symbols": ["AAPL", "MSFT", "NVDA"],
                "source": "mock",
                "asof_utc": "2025-01-02T00:00:00Z",
                "tags": ["daily"],
                "count": 3,
            }
        ]

    def save_watchlist(
        self, payload: Dict[str, Any], *, request_id: str | None = None
    ) -> Dict[str, Any]:
        return {
            "bucket": payload.get("bucket", "mock"),
            "count": len(payload.get("symbols", [])),
        }

    def signals(self, symbol: str) -> List[Dict[str, Any]]:
        return [{"timestamp": "2025-01-02T00:00:00Z", "value": 0.5, "symbol": symbol}]


@dataclass
class MockHealthService:
    def live(self) -> Dict[str, Any]:
        return {"status": "ok"}

    def ready(self) -> Dict[str, Any]:
        return {"status": "ok"}

    def openapi(self) -> Dict[str, Any]:
        return {}


@dataclass
class MockServices:
    models: MockModelsService = field(default_factory=MockModelsService)
    backtests: MockBacktestService = field(default_factory=MockBacktestService)
    orders: MockOrdersService = field(default_factory=MockOrdersService)
    trading: MockTradingService = field(default_factory=MockTradingService)
    watchlists: MockWatchlistService = field(default_factory=MockWatchlistService)
    health: MockHealthService = field(default_factory=MockHealthService)
