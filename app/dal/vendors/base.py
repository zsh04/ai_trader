from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Iterable, Optional

from app.dal.schemas import Bars


@dataclass(slots=True)
class FetchRequest:
    symbol: str
    start: Optional[datetime]
    end: Optional[datetime]
    interval: str
    limit: Optional[int] = None


class VendorClient(abc.ABC):
    """Base class for market data vendor implementations."""

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    @abc.abstractmethod
    def fetch_bars(self, request: FetchRequest) -> Bars:
        """Fetch historical bars synchronously."""

    def supports_streaming(self) -> bool:
        return False

    async def stream_bars(
        self, symbols: Iterable[str], interval: str
    ) -> AsyncIterator[dict]:
        raise NotImplementedError(
            f"Vendor {self.name} does not implement streaming bars."
        )
