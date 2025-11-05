from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, Iterable, List, Optional, Tuple

from loguru import logger

try:  # optional OTEL instrumentation
    from opentelemetry import trace

    _tracer = trace.get_tracer(__name__)
except Exception:  # pragma: no cover - instrumentation optional
    _tracer = None

from sqlalchemy import text

from app.adapters.db.postgres import get_engine
from app.agent.probabilistic.regime import RegimeAnalysisAgent, RegimeSnapshot
from app.agent.probabilistic.signal_filter import FilterConfig, SignalFilteringAgent
from app.dal.cache import (
    store_bars_to_parquet,
    store_regimes_to_parquet,
    store_signals_to_parquet,
)
from app.dal.kalman import KalmanConfig
from app.dal.results import ProbabilisticBatch, ProbabilisticStreamFrame
from app.dal.schemas import Bars, SignalFrame
from app.dal.streaming import StreamingManager
from app.dal.vendors.alpaca import AlpacaVendor
from app.dal.vendors.alphavantage import AlphaVantageVendor
from app.dal.vendors.base import FetchRequest, VendorClient
from app.dal.vendors.finnhub import FinnhubVendor


class MarketDataDAL:
    """Unified interface for historical and streaming market data."""

    def __init__(
        self,
        *,
        cache_dir: Optional[Path] = Path("artifacts/marketdata/cache"),
        vendor_clients: Optional[Dict[str, VendorClient]] = None,
        kalman_config: Optional[KalmanConfig] = None,
        filter_config: Optional[FilterConfig] = None,
        regime_params: Optional[Dict[str, object]] = None,
        enable_postgres_metadata: bool = True,
    ) -> None:
        self.cache_dir = cache_dir
        self.vendor_clients = vendor_clients or self._default_vendors()
        base_filter_config = filter_config or FilterConfig()
        if kalman_config is not None:
            base_filter_config = FilterConfig(
                kalman=kalman_config,
                butterworth_cutoff=base_filter_config.butterworth_cutoff,
                butterworth_order=base_filter_config.butterworth_order,
                ema_span=base_filter_config.ema_span,
            )
        self.filter_config = base_filter_config
        self.kalman_config = self.filter_config.kalman or KalmanConfig()
        self.regime_params: Dict[str, object] = dict(regime_params or {})
        self.enable_postgres_metadata = enable_postgres_metadata
        self._engine = get_engine() if enable_postgres_metadata else None
        if self._engine is not None:
            self._ensure_metadata_table()

    def _default_vendors(self) -> Dict[str, VendorClient]:
        return {
            "alpaca": AlpacaVendor(),
            "alphavantage": AlphaVantageVendor(),
            "finnhub": FinnhubVendor(),
        }

    def fetch_bars(
        self,
        symbol: str,
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: str = "1Min",
        vendor: str = "alpaca",
        limit: Optional[int] = None,
    ) -> ProbabilisticBatch:
        client = self._get_vendor(vendor)
        request = FetchRequest(
            symbol=symbol,
            start=start,
            end=end,
            interval=interval,
            limit=limit,
        )

        def _call_fetch():
            return client.fetch_bars(request)

        span_ctx = (
            _tracer.start_as_current_span("dal.fetch_bars", attributes={"vendor": vendor})
            if _tracer
            else contextlib.nullcontext()
        )
        with span_ctx:
            bars = _call_fetch()

        signals, regimes = self._run_probabilistic_pipeline(bars)
        cache_paths: Dict[str, Path] = {}
        if self.cache_dir:
            bars_path = store_bars_to_parquet(bars, self.cache_dir)
            cache_paths["bars"] = bars_path
            signals_path = store_signals_to_parquet(signals, self.cache_dir)
            if signals_path:
                cache_paths["signals"] = signals_path
            regimes_path = store_regimes_to_parquet(regimes, self.cache_dir)
            if regimes_path:
                cache_paths["regimes"] = regimes_path
        bars_path = cache_paths.get("bars") if cache_paths else None
        if self._engine is not None:
            self._persist_metadata(bars, bars_path)
        return ProbabilisticBatch(
            bars=bars,
            signals=signals,
            regimes=regimes,
            cache_paths=cache_paths,
        )

    async def stream_bars(
        self,
        symbols: Iterable[str],
        *,
        interval: str = "1Min",
        vendor: str = "alpaca",
    ) -> AsyncIterator[ProbabilisticStreamFrame]:
        client = self._get_vendor(vendor)
        if not client.supports_streaming():
            raise RuntimeError(f"Vendor {vendor} does not support streaming transport")

        def backfill(request: FetchRequest) -> Iterable[dict]:
            bars = client.fetch_bars(request)
            for bar in bars.data:
                yield {
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp,
                    "close": bar.close,
                    "volume": bar.volume,
                }

        manager = StreamingManager(
            client,
            interval,
            filter_config=self.filter_config,
            regime_params=self.regime_params,
            fetch_backfill=backfill,
        )
        async for frame in manager.stream(symbols):
            yield frame

    def _get_vendor(self, vendor: str) -> VendorClient:
        try:
            return self.vendor_clients[vendor]
        except KeyError as exc:  # pragma: no cover - misconfiguration guard
            raise ValueError(f"Unknown vendor: {vendor}") from exc

    def _run_probabilistic_pipeline(
        self, bars: Bars
    ) -> Tuple[List[SignalFrame], List[RegimeSnapshot]]:
        filter_agent = SignalFilteringAgent(self.filter_config)
        signals = filter_agent.run(bars)
        regime_agent = RegimeAnalysisAgent(**self.regime_params)
        regimes = regime_agent.classify(signals)
        return signals, regimes

    def _ensure_metadata_table(self) -> None:
        if self._engine is None:
            return
        ddl = text(
            """
            CREATE TABLE IF NOT EXISTS market_data_snapshots (
                id BIGSERIAL PRIMARY KEY,
                vendor TEXT NOT NULL,
                symbol TEXT NOT NULL,
                start_ts TIMESTAMPTZ,
                end_ts TIMESTAMPTZ,
                bar_count INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                storage_path TEXT
            )
            """
        )
        with self._engine.begin() as conn:  # pragma: no cover - exercised in integration
            conn.execute(ddl)

    def _persist_metadata(self, bars: Bars, cache_path: Optional[Path]) -> None:
        if self._engine is None:
            return
        if not bars.data:
            return
        start_ts = bars.data[0].timestamp
        end_ts = bars.data[-1].timestamp
        storage_path = str(cache_path.resolve()) if cache_path else None
        insert_sql = text(
            """
            INSERT INTO market_data_snapshots (vendor, symbol, start_ts, end_ts, bar_count, storage_path)
            VALUES (:vendor, :symbol, :start_ts, :end_ts, :bar_count, :storage_path)
            """
        )
        with self._engine.begin() as conn:  # pragma: no cover - exercised in integration
            conn.execute(
                insert_sql,
                {
                    "vendor": bars.vendor,
                    "symbol": bars.symbol,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "bar_count": len(bars.data),
                    "storage_path": storage_path,
                },
            )


__all__ = ["MarketDataDAL"]
