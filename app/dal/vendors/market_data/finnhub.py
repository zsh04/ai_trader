from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator, Iterable, Optional

import websockets
from loguru import logger

from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient
from app.settings import get_market_data_settings
from app.utils.http import http_get

_SUPPORTED_DAILY = {"1day", "1Day", "1D"}


class FinnhubVendor(VendorClient):
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__("finnhub")
        self.api_key = api_key or get_market_data_settings().finnhub_key
        if not self.api_key:
            logger.warning("Finnhub API key not configured; fetches will fail")

    def fetch_bars(self, request: FetchRequest) -> Bars:
        if not self.api_key:
            raise RuntimeError("Finnhub API key missing")

        interval = (request.interval or "").strip() or "1Day"
        if interval not in _SUPPORTED_DAILY:
            logger.debug(
                "Finnhub intraday disabled for interval=%s; returning empty dataset",
                interval,
            )
            return Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")

        return self._fetch_daily_quote(request)

    def supports_streaming(self) -> bool:
        return bool(self.api_key)

    async def stream_bars(
        self, symbols: Iterable[str], interval: str
    ) -> AsyncIterator[dict]:
        if not self.api_key:
            raise RuntimeError("Finnhub API key missing")
        # Finnhub streams trade ticks; downstream components aggregate into bars.
        query = f"wss://ws.finnhub.io?token={self.api_key}"
        subscribe_messages = [
            json.dumps({"type": "subscribe", "symbol": sym.upper()}) for sym in symbols
        ]

        async for message in _finnhub_stream(
            query, subscribe_messages
        ):  # pragma: no cover
            if message.get("type") != "trade":
                continue
            for trade in message.get("data", []):
                price = trade.get("p")
                volume = trade.get("v", 0.0)
                ts = datetime.fromtimestamp(trade.get("t", 0) / 1000, tz=timezone.utc)
                yield {
                    "symbol": trade.get("s"),
                    "timestamp": ts,
                    "price": price,
                    "volume": volume,
                    "source": "trade",
                    "interval": interval,
                }

    def _fetch_daily_quote(self, request: FetchRequest) -> Bars:
        params = {
            "symbol": request.symbol.upper(),
            "token": self.api_key,
        }
        status, payload = http_get(f"{self.BASE_URL}/quote", params=params)
        if status != 200 or not isinstance(payload, dict):
            logger.warning(
                "Finnhub quote fetch failed symbol={} status={} payload={}",
                request.symbol,
                status,
                payload,
            )
            return Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")

        timestamp = payload.get("t")
        if not timestamp:
            logger.debug(
                "Finnhub quote missing timestamp for symbol=%s", request.symbol
            )
            return Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")

        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        bar = Bar(
            symbol=request.symbol.upper(),
            vendor=self.name,
            timestamp=dt,
            open=float(payload.get("o", 0.0)),
            high=float(payload.get("h", 0.0)),
            low=float(payload.get("l", 0.0)),
            close=float(payload.get("c", payload.get("pc", 0.0))),
            volume=float(payload.get("v", 0.0)) if "v" in payload else 0.0,
            timezone="UTC",
            source="daily_quote",
        )
        bars = Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
        bars.append(bar)
        return bars


async def _finnhub_stream(
    url: str, subscribe_messages: list[str], reconnect_delay: float = 5.0
):
    while True:  # pragma: no cover - network path
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                for msg in subscribe_messages:
                    await ws.send(msg)
                async for raw in ws:
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        logger.debug("finnhub stream non-json payload={}", raw)
        except Exception as exc:
            logger.warning("Finnhub stream reconnecting after error: {}", exc)
            await asyncio.sleep(reconnect_delay)
