from __future__ import annotations

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

from app.adapters.db.postgres import get_session
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
from app.dal.vendors.base import FetchRequest, VendorClient
from app.dal.vendors.market_data import (
    AlpacaVendor,
    AlphaVantageDailyVendor,
    AlphaVantageVendor,
    FinnhubVendor,
    MarketstackVendor,
    TwelveDataVendor,
    YahooVendor,
)
from app.db.repositories.market import MarketRepository
from app.eventbus.publisher import publish_event


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

    def _default_vendors(self) -> Dict[str, VendorClient]:
        return {
            "alpaca": AlpacaVendor(),
            "alphavantage": AlphaVantageVendor(),
            "alphavantage_eod": AlphaVantageDailyVendor(),
            "finnhub": FinnhubVendor(),
            "yahoo": YahooVendor(),
            "twelvedata": TwelveDataVendor(),
            "marketstack": MarketstackVendor(),
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
        if vendor == "alphavantage" and interval in {"1Day", "1day", "1D"}:
            vendor = "alphavantage_eod"

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
            _tracer.start_as_current_span(
                "dal.fetch_bars", attributes={"vendor": vendor}
            )
            if _tracer
            else contextlib.nullcontext()
        )
        with span_ctx:
            bars = _call_fetch()
        self._publish_bar_snapshot(bars, vendor, request)

        signals, regimes = self._run_probabilistic_pipeline(bars)
        self._publish_probabilistic_snapshots(
            bars.symbol, bars.vendor, request.interval, signals, regimes
        )
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

    def _persist_metadata(self, bars: Bars, cache_path: Optional[Path]) -> None:
        if not self.enable_postgres_metadata or not bars.data:
            return
        try:
            session = get_session()
        except RuntimeError:
            logger.debug(
                "[dal] Postgres session unavailable; skipping metadata persist"
            )
            return

        try:
            repo = MarketRepository(session)
            repo.upsert_symbols(
                [
                    {
                        "symbol": bars.symbol.upper(),
                        "name": None,
                        "asset_class": "equity",
                        "primary_exchange": None,
                        "currency": "USD",
                        "status": "active",
                    }
                ]
            )

            common_features = {
                "timezone": bars.timezone,
                "vendor": bars.vendor,
                "cache_path": str(cache_path) if cache_path else None,
            }
            snapshots = []
            for bar in bars.data:
                snapshots.append(
                    {
                        "symbol": bar.symbol.upper(),
                        "vendor": bars.vendor,
                        "ts_utc": bar.timestamp,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        "features": {**common_features, "source": bar.source},
                    }
                )
            repo.record_price_snapshots(snapshots)
            session.commit()
        except Exception as exc:  # pragma: no cover - defensive
            session.rollback()
            logger.warning("[dal] failed to persist price snapshots: {}", exc)
        finally:
            session.close()

    def _publish_bar_snapshot(
        self, bars: Bars, vendor: str, request: FetchRequest
    ) -> None:
        try:
            payload = {
                "symbol": bars.symbol,
                "vendor": vendor,
                "interval": request.interval,
                "count": len(bars.data),
                "start": bars.data[0].timestamp if bars.data else None,
                "end": bars.data[-1].timestamp if bars.data else None,
            }
            publish_event("EH_HUB_BARS", payload)
        except Exception:  # pragma: no cover - telemetry only
            logger.debug("[dal] failed to emit bars event for %s", bars.symbol)

    def _publish_probabilistic_snapshots(
        self,
        symbol: str,
        vendor: str,
        interval: str | None,
        signals: List[SignalFrame],
        regimes: List[RegimeSnapshot],
    ) -> None:
        try:
            publish_event(
                "EH_HUB_SIGNALS",
                {
                    "symbol": symbol,
                    "vendor": vendor,
                    "interval": interval,
                    "count": len(signals),
                },
            )
            publish_event(
                "EH_HUB_REGIMES",
                {
                    "symbol": symbol,
                    "vendor": vendor,
                    "interval": interval,
                    "count": len(regimes),
                },
            )
        except Exception:  # pragma: no cover
            logger.debug("[dal] failed to emit probabilistic events for %s", symbol)


__all__ = ["MarketDataDAL"]
