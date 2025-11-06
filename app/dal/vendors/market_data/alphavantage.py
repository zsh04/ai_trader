from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient
from app.settings import get_market_data_settings
from app.utils.http import http_get


class AlphaVantageVendor(VendorClient):
    BASE_URL = "https://www.alphavantage.co/query"
    SUPPORTED_INTERVALS = {"1min", "5min", "15min", "30min", "60min"}

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__("alphavantage")
        self.api_key = api_key or get_market_data_settings().alphavantage_key
        if not self.api_key:
            logger.warning("AlphaVantage API key not configured; fetches will fail")

    def fetch_bars(self, request: FetchRequest) -> Bars:
        if not self.api_key:
            raise RuntimeError("AlphaVantage API key missing")

        interval = _normalize_interval(request.interval)
        if interval not in self.SUPPORTED_INTERVALS:
            raise ValueError(
                "AlphaVantage only supports intraday intervals "
                "{'1Min','5Min','15Min','30Min','60Min'}"
            )

        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": request.symbol.upper(),
            "interval": interval,
            "apikey": self.api_key,
            "outputsize": "full" if request.limit is None else "compact",
        }
        status, payload = http_get(self.BASE_URL, params=params)
        if status != 200 or not isinstance(payload, dict):
            logger.warning(
                "alphavantage fetch failed symbol={} status={} payload={}",
                request.symbol,
                status,
                payload,
            )
            return Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")

        series_key = next(
            (k for k in payload.keys() if k.startswith("Time Series")), None
        )
        if not series_key:
            logger.warning(
                "alphavantage response missing time series: {}", payload.keys()
            )
            return Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")

        raw_series = payload.get(series_key, {})
        items = list(raw_series.items())
        if request.limit:
            items = items[: request.limit]

        bars = Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
        for ts_str, entry in items:
            try:
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                bars.append(
                    Bar(
                        symbol=request.symbol.upper(),
                        vendor=self.name,
                        timestamp=ts,
                        open=float(entry.get("1. open", 0.0)),
                        high=float(entry.get("2. high", 0.0)),
                        low=float(entry.get("3. low", 0.0)),
                        close=float(entry.get("4. close", 0.0)),
                        volume=float(entry.get("5. volume", 0.0)),
                        timezone="UTC",
                        source="historical",
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.debug("alphavantage parse error ts={} err={}", ts_str, exc)
        return bars


def _normalize_interval(interval: Optional[str]) -> str:
    if not interval:
        return ""
    val = interval.strip()
    if not val:
        return ""
    aliases = {
        "1m": "1min",
        "1minute": "1min",
        "1min": "1min",
        "1Min": "1min",
        "5m": "5min",
        "5minute": "5min",
        "5Min": "5min",
        "15m": "15min",
        "15Min": "15min",
        "30m": "30min",
        "30Min": "30min",
        "60m": "60min",
        "60Min": "60min",
        "1h": "60min",
        "1H": "60min",
    }
    return aliases.get(val, aliases.get(val.lower(), val.lower()))
