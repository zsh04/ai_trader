from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List

import pytest

from app.dal.manager import MarketDataDAL
from app.dal.results import ProbabilisticStreamFrame
from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient


class HybridVendor(VendorClient):
    def __init__(self, bars: List[Bar], stream_events: List[dict]) -> None:
        super().__init__("hybrid")
        self._bars = bars
        self._stream_events = stream_events

    def fetch_bars(self, request: FetchRequest) -> Bars:
        out = Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
        for bar in self._bars:
            if request.start and bar.timestamp < request.start:
                continue
            if request.end and bar.timestamp > request.end:
                continue
            out.append(bar)
            if request.limit and len(out.data) >= request.limit:
                break
        if not out.data:
            # provide minimal response so consumers still get structure
            for bar in self._bars:
                out.append(bar)
                break
        return out

    def supports_streaming(self) -> bool:
        return True

    async def stream_bars(self, symbols: Iterable[str], interval: str):  # type: ignore[override]
        for payload in self._stream_events:
            await asyncio.sleep(0)
            yield payload


@pytest.mark.anyio("asyncio")
async def test_probabilistic_pipeline_end_to_end(tmp_path: Path):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    historical_bars = [
        Bar(
            symbol="AAPL",
            vendor="hybrid",
            timestamp=base + timedelta(minutes=idx),
            open=100 + idx,
            high=101 + idx,
            low=99 + idx,
            close=100 + idx,
            volume=1_000 + idx * 10,
            timezone="UTC",
            source="historical",
        )
        for idx in range(10)
    ]

    stream_events = [
        {
            "symbol": "AAPL",
            "timestamp": base + timedelta(minutes=5),
            "price": 105.0,
            "volume": 1_200,
        },
        {
            # skip ahead to trigger deterministic backfill
            "symbol": "AAPL",
            "timestamp": base + timedelta(minutes=9),
            "price": 109.0,
            "volume": 1_300,
        },
    ]

    vendor = HybridVendor(historical_bars, stream_events)
    dal = MarketDataDAL(
        cache_dir=tmp_path,
        vendor_clients={"hybrid": vendor},
        enable_postgres_metadata=False,
    )

    batch = dal.fetch_bars("AAPL", vendor="hybrid", limit=5)
    assert batch.bars.symbol == "AAPL"
    assert len(batch.signals) == 5
    assert len(batch.regimes) == 5
    assert all(frame.butterworth_price is not None for frame in batch.signals)
    assert all(frame.ema_price is not None for frame in batch.signals)
    assert batch.regimes[-1].regime in {"trend_up", "sideways", "calm"}

    stream_frames: list[ProbabilisticStreamFrame] = []
    target_ts = stream_events[-1]["timestamp"]
    async for payload in dal.stream_bars(["AAPL"], vendor="hybrid", interval="1Min"):
        stream_frames.append(payload)
        if payload.signal.timestamp >= target_ts:
            break
        if len(stream_frames) > 12:
            break

    assert len(stream_frames) >= len(stream_events)
    assert stream_frames[0].signal.timestamp > batch.bars.data[0].timestamp
    assert stream_frames[-1].signal.timestamp >= target_ts
    assert all(frame.signal.butterworth_price is not None for frame in stream_frames)
    assert all(frame.regime.symbol == "AAPL" for frame in stream_frames)
    assert stream_frames[-1].regime.regime in {
        "trend_up",
        "sideways",
        "calm",
        "high_volatility",
    }
