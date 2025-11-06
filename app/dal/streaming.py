from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Callable, Deque, Dict, Iterable, List, Optional

from loguru import logger

from app.agent.probabilistic.regime import RegimeAnalysisAgent, RegimeSnapshot
from app.agent.probabilistic.signal_filter import FilterConfig, SignalFilteringAgent
from app.dal.results import ProbabilisticStreamFrame
from app.dal.schemas import SignalFrame
from app.dal.vendors.base import FetchRequest, VendorClient

_INTERVAL_SECONDS = {
    "1Min": 60,
    "5Min": 300,
    "15Min": 900,
    "30Min": 1_800,
    "60Min": 3_600,
    "1Hour": 3_600,
    "1Day": 86_400,
}


def interval_to_seconds(interval: str) -> int:
    return _INTERVAL_SECONDS.get(interval, 60)


class _PipelineState:
    def __init__(
        self,
        symbol: str,
        vendor: str,
        filter_config: FilterConfig,
        regime_params: Dict[str, object],
    ) -> None:
        self.symbol = symbol
        self.vendor = vendor
        self.filter_agent = SignalFilteringAgent(filter_config)
        self.regime_agent = RegimeAnalysisAgent(**regime_params)
        buffer_len = max(self.regime_agent.window * 3, 64)
        self.buffer: Deque[SignalFrame] = deque(maxlen=buffer_len)

    def process(
        self, timestamp: datetime, price: float, volume: float
    ) -> ProbabilisticStreamFrame:
        signal = self.filter_agent.step(
            symbol=self.symbol,
            vendor=self.vendor,
            timestamp=timestamp,
            price=price,
            volume=volume,
        )
        self.buffer.append(signal)
        regime_snapshots = self.regime_agent.classify(list(self.buffer))
        regime = (
            regime_snapshots[-1]
            if regime_snapshots
            else RegimeSnapshot(
                symbol=self.symbol,
                timestamp=signal.timestamp,
                regime="unknown",
                volatility=0.0,
                uncertainty=signal.uncertainty,
                momentum=0.0,
            )
        )
        return ProbabilisticStreamFrame(signal=signal, regime=regime)


class StreamingManager:
    def __init__(
        self,
        vendor: VendorClient,
        interval: str,
        filter_config: Optional[FilterConfig] = None,
        regime_params: Optional[Dict[str, object]] = None,
        *,
        max_queue: int = 1024,
        gap_threshold: Optional[float] = None,
        fetch_backfill: Optional[Callable[[FetchRequest], Iterable[dict]]] = None,
    ) -> None:
        self.vendor = vendor
        self.interval = interval
        self.filter_config = filter_config or FilterConfig()
        self.regime_params: Dict[str, object] = dict(regime_params or {})
        self.max_queue = max_queue
        self.gap_seconds = gap_threshold or interval_to_seconds(interval) * 3
        self.fetch_backfill = fetch_backfill

    async def stream(
        self, symbols: Iterable[str]
    ) -> AsyncIterator[ProbabilisticStreamFrame]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue)
        producer_task = asyncio.create_task(self._producer(queue, symbols))
        pipeline_map: Dict[str, _PipelineState] = {
            sym.upper(): _PipelineState(
                sym.upper(), self.vendor.name, self.filter_config, self.regime_params
            )
            for sym in symbols
        }
        last_seen: Dict[str, datetime] = {sym.upper(): None for sym in symbols}  # type: ignore

        try:
            while True:
                event = await queue.get()
                if event.get("__end__"):
                    break
                symbol = (event.get("symbol") or event.get("S") or "").upper()
                if not symbol:
                    continue
                ts = event.get("timestamp")
                if isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts, tz=timezone.utc)
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                if not isinstance(ts, datetime):
                    ts = datetime.now(timezone.utc)
                ts = ts.astimezone(timezone.utc)

                price = event.get("close") or event.get("price") or event.get("p")
                if price is None:
                    continue
                volume = float(event.get("volume") or event.get("v") or 0.0)

                last_ts = last_seen.get(symbol)
                frames_before = []
                if last_ts and (ts - last_ts).total_seconds() > self.gap_seconds:
                    frames_before = await self._backfill(
                        symbol, last_ts, ts, pipeline_map[symbol]
                    )

                for frame in frames_before:
                    last_seen[symbol] = frame.signal.timestamp
                    yield frame

                pipeline = pipeline_map.setdefault(
                    symbol,
                    _PipelineState(
                        symbol, self.vendor.name, self.filter_config, self.regime_params
                    ),
                )
                result = pipeline.process(ts, float(price), volume)
                last_seen[symbol] = result.signal.timestamp
                yield result
        finally:
            producer_task.cancel()
            with contextlib.suppress(Exception):
                await producer_task

    async def _producer(self, queue: asyncio.Queue, symbols: Iterable[str]) -> None:
        async for payload in self.vendor.stream_bars(symbols, self.interval):
            await self._put_with_backpressure(queue, payload)
        await self._put_with_backpressure(queue, {"__end__": True})

    async def _put_with_backpressure(self, queue: asyncio.Queue, payload: dict) -> None:
        while True:
            try:
                queue.put_nowait(payload)
                return
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - race
                    await asyncio.sleep(0)

    async def _backfill(
        self,
        symbol: str,
        last_ts: datetime,
        current_ts: datetime,
        pipeline: _PipelineState,
    ) -> List[ProbabilisticStreamFrame]:
        if not self.fetch_backfill:
            logger.debug(
                "stream gap detected but no backfill handler configured symbol={} gap={}s",
                symbol,
                (current_ts - last_ts).total_seconds(),
            )
            return []
        request = FetchRequest(
            symbol=symbol,
            start=last_ts - timedelta(seconds=self.gap_seconds),
            end=current_ts,
            interval=self.interval,
            limit=None,
        )
        frames: List[SignalFrame] = []
        loop = asyncio.get_running_loop()
        raw_records = await loop.run_in_executor(
            None, lambda: list(self.fetch_backfill(request) or [])
        )
        raw_records.sort(key=lambda item: item.get("timestamp"))
        for record in raw_records:
            ts = record.get("timestamp")
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts, tz=timezone.utc)
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if not isinstance(ts, datetime):
                continue
            ts = ts.astimezone(timezone.utc)
            price = record.get("close") or record.get("price")
            if price is None:
                continue
            volume = float(record.get("volume") or 0.0)
            frames.append(pipeline.process(ts, float(price), volume))
        return frames


__all__ = ["StreamingManager", "interval_to_seconds"]
