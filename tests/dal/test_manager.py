from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.dal.manager import MarketDataDAL
from app.dal.results import ProbabilisticStreamFrame
from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient


class FakeVendor(VendorClient):
    def __init__(self) -> None:
        super().__init__("fake")

    def fetch_bars(self, request: FetchRequest) -> Bars:
        bars = Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        for idx in range(3):
            bars.append(
                Bar(
                    symbol=request.symbol.upper(),
                    vendor=self.name,
                    timestamp=base + timedelta(minutes=idx),
                    open=100 + idx,
                    high=101 + idx,
                    low=99 + idx,
                    close=100 + idx,
                    volume=1_000 + idx,
                    timezone="UTC",
                    source="test",
                )
            )
        return bars


class StreamingVendor(VendorClient):
    def __init__(self, events: list[dict]) -> None:
        super().__init__("stream_fake")
        self._events = events

    def fetch_bars(self, request: FetchRequest) -> Bars:
        bars = Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
        base = request.start or datetime.now(timezone.utc)
        bars.append(
            Bar(
                symbol=request.symbol.upper(),
                vendor=self.name,
                timestamp=base + timedelta(seconds=30),
                open=200,
                high=201,
                low=199,
                close=200,
                volume=5_000,
                timezone="UTC",
                source="backfill",
            )
        )
        return bars

    def supports_streaming(self) -> bool:
        return True

    async def stream_bars(self, symbols, interval: str):  # type: ignore[override]
        for payload in self._events:
            await asyncio.sleep(0)
            yield payload


def test_market_data_dal_fetch(tmp_path: Path, monkeypatch):
    dal = MarketDataDAL(
        cache_dir=tmp_path,
        vendor_clients={"fake": FakeVendor()},
        enable_postgres_metadata=False,
    )
    batch = dal.fetch_bars("AAPL", vendor="fake")
    assert batch.bars.symbol == "AAPL"
    assert len(batch.bars.data) == 3
    assert len(batch.signals) == 3
    assert len(batch.regimes) == 3
    assert "bars" in batch.cache_paths
    assert "signals" in batch.cache_paths
    assert "regimes" in batch.cache_paths
    parquet_files = list(tmp_path.glob("*.parquet"))
    assert parquet_files, "expected cached parquet output"


@pytest.mark.anyio("asyncio")
async def test_market_data_dal_stream_backfill(tmp_path: Path):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    events = [
        {
            "symbol": "AAPL",
            "timestamp": base,
            "price": 210.0,
            "volume": 1000,
        },
        {
            # gap that should trigger backfill
            "symbol": "AAPL",
            "timestamp": base + timedelta(minutes=5),
            "price": 215.0,
            "volume": 1200,
        },
    ]
    vendor = StreamingVendor(events)
    dal = MarketDataDAL(
        cache_dir=tmp_path,
        vendor_clients={"stream": vendor},
        enable_postgres_metadata=False,
    )

    frames: list[ProbabilisticStreamFrame] = []
    async for frame in dal.stream_bars(["AAPL"], vendor="stream", interval="1Min"):
        frames.append(frame)
        if len(frames) >= 3:
            break

    assert frames, "expected streamed frames"
    symbols = {frame.signal.symbol for frame in frames}
    assert symbols == {"AAPL"}
    assert all(frame.regime.symbol == "AAPL" for frame in frames)
