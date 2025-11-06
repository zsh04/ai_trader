from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator, Iterable, Optional

import websockets
from loguru import logger

from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient
from app.utils.env import (
    ALPACA_API_KEY,
    ALPACA_API_SECRET,
    ALPACA_DATA_BASE_URL,
    ALPACA_FEED,
)
from app.utils.http import alpaca_headers, http_get


class AlpacaVendor(VendorClient):
    """HTTP + WebSocket client for Alpaca market data."""

    def __init__(self, feed: Optional[str] = None) -> None:
        super().__init__("alpaca")
        self.feed = (feed or ALPACA_FEED or "iex").lower()

    def fetch_bars(self, request: FetchRequest) -> Bars:
        params: dict[str, str | int] = {
            "symbols": request.symbol.upper(),
            "timeframe": request.interval,
            "feed": self.feed,
        }
        if request.limit:
            params["limit"] = int(request.limit)
        if request.start:
            params["start"] = request.start.astimezone(timezone.utc).isoformat()
        if request.end:
            params["end"] = request.end.astimezone(timezone.utc).isoformat()

        url = f"{ALPACA_DATA_BASE_URL}/stocks/bars"
        status, payload = http_get(url, params=params, headers=alpaca_headers())
        if status != 200:
            logger.warning(
                "alpaca fetch_bars failed symbol={} status={} payload={}",
                request.symbol,
                status,
                payload,
            )
            return Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")

        raw_bars = ((payload or {}).get("bars") or {}).get(request.symbol.upper(), [])
        bars = Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
        for entry in raw_bars:
            ts = entry.get("t")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            elif not isinstance(ts, datetime):
                continue
            bars.append(
                Bar(
                    symbol=request.symbol.upper(),
                    vendor=self.name,
                    timestamp=ts.astimezone(timezone.utc),
                    open=float(entry.get("o", 0.0)),
                    high=float(entry.get("h", 0.0)),
                    low=float(entry.get("l", 0.0)),
                    close=float(entry.get("c", 0.0)),
                    volume=float(entry.get("v", 0.0)),
                    timezone="UTC",
                    source="historical",
                )
            )
        return bars

    def supports_streaming(self) -> bool:
        return bool(ALPACA_API_KEY and ALPACA_API_SECRET)

    async def stream_bars(
        self, symbols: Iterable[str], interval: str
    ) -> AsyncIterator[dict]:
        if not self.supports_streaming():
            raise RuntimeError("Alpaca streaming requires API credentials")
        auth_payload = {
            "action": "auth",
            "key": ALPACA_API_KEY,
            "secret": ALPACA_API_SECRET,
        }
        subscribe_payload = {
            "action": "subscribe",
            "bars": [sym.upper() for sym in symbols],
        }
        stream_url = f"wss://stream.data.alpaca.markets/v2/{self.feed}"

        async for message in _alpaca_stream(  # pragma: no cover - network IO
            stream_url, auth_payload, subscribe_payload
        ):
            if message.get("T") != "b":
                continue
            yield {
                "symbol": message.get("S"),
                "timestamp": datetime.fromtimestamp(
                    message.get("t", 0) / 1_000_000_000, tz=timezone.utc
                ),
                "open": message.get("o"),
                "high": message.get("h"),
                "low": message.get("l"),
                "close": message.get("c"),
                "volume": message.get("v"),
                "source": "stream",
            }


async def _alpaca_stream(
    url: str,
    auth_payload: dict,
    subscribe_payload: dict,
    reconnect_delay: float = 3.0,
):
    """Reconnect-aware streaming helper for Alpaca bars."""
    while True:  # pragma: no cover - network IO
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(auth_payload))
                await ws.send(json.dumps(subscribe_payload))
                async for raw in ws:
                    try:
                        payload = json.loads(raw)
                        if isinstance(payload, list):
                            for item in payload:
                                yield item
                        else:
                            yield payload
                    except json.JSONDecodeError:
                        logger.debug("alpaca stream non-json payload={}", raw)
        except Exception as exc:
            logger.warning("alpaca stream reconnecting after error: {}", exc)
            await asyncio.sleep(reconnect_delay)
