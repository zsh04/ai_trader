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


_RESOLUTION_MAP = {
    "1Min": "1",
    "5Min": "5",
    "15Min": "15",
    "30Min": "30",
    "60Min": "60",
    "1Hour": "60",
    "1Day": "D",
}


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

        resolution = _RESOLUTION_MAP.get(request.interval)
        if not resolution:
            raise ValueError(f"Unsupported Finnhub interval: {request.interval}")

        if not request.start or not request.end:
            raise ValueError("Finnhub fetch requires explicit start and end timestamps")

        params = {
            "symbol": request.symbol.upper(),
            "resolution": resolution,
            "from": int(request.start.timestamp()),
            "to": int(request.end.timestamp()),
            "token": self.api_key,
        }
        status, payload = http_get(f"{self.BASE_URL}/stock/candle", params=params)
        if status != 200 or not isinstance(payload, dict) or payload.get("s") != "ok":
            logger.warning("Finnhub candle fetch failed symbol={} status={} payload={} ",
                           request.symbol, status, payload)
            return Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")

        bars = Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
        timestamps = payload.get("t", [])
        opens = payload.get("o", [])
        highs = payload.get("h", [])
        lows = payload.get("l", [])
        closes = payload.get("c", [])
        volumes = payload.get("v", [])
        for idx, ts in enumerate(timestamps):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            bars.append(
                Bar(
                    symbol=request.symbol.upper(),
                    vendor=self.name,
                    timestamp=dt,
                    open=float(opens[idx]),
                    high=float(highs[idx]),
                    low=float(lows[idx]),
                    close=float(closes[idx]),
                    volume=float(volumes[idx]),
                    timezone="UTC",
                    source="historical",
                )
            )
        return bars

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
            json.dumps({"type": "subscribe", "symbol": sym.upper()})
            for sym in symbols
        ]

        async for message in _finnhub_stream(query, subscribe_messages):  # pragma: no cover
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


async def _finnhub_stream(url: str, subscribe_messages: list[str], reconnect_delay: float = 5.0):
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
