from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from loguru import logger

from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient
from app.dal.vendors.market_data.twelvedata import TwelveDataVendor
from app.dal.vendors.market_data.yahoo import YahooVendor
from app.settings import get_market_data_settings
from app.utils.http import http_get


class AlphaVantageDailyVendor(VendorClient):
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(
        self,
        api_key: Optional[str] = None,
        fallback_vendors: Optional[Sequence[VendorClient]] = None,
    ) -> None:
        super().__init__("alphavantage_eod")
        self.api_key = api_key or get_market_data_settings().alphavantage_key
        if not self.api_key:
            logger.warning("AlphaVantage API key not configured; daily fetches will fail")
        self._fallback_vendors: Sequence[VendorClient] = (
            list(fallback_vendors)
            if fallback_vendors is not None
            else [YahooVendor(), TwelveDataVendor()]
        )

    def fetch_bars(self, request: FetchRequest) -> Bars:
        if not self.api_key:
            raise RuntimeError("AlphaVantage API key missing")

        interval = (request.interval or "1Day").strip()
        if interval not in {"1Day", "1day", "1D"}:
            raise ValueError("AlphaVantage daily vendor only supports 1Day interval")

        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": request.symbol.upper(),
            "apikey": self.api_key,
            "outputsize": "full" if request.limit is None else "compact",
        }
        status, payload = http_get(self.BASE_URL, params=params)
        if status != 200 or not isinstance(payload, dict):
            logger.info(
                "AlphaVantage daily fetch failed symbol={} status={} -- attempting fallback",
                request.symbol,
                status,
            )
            return self._fallback_fetch(request)

        series_key = next(
            (k for k in payload.keys() if k.startswith("Time Series")), None
        )
        if not series_key:
            logger.debug(
                "AlphaVantage daily response missing time series for symbol=%s",
                request.symbol,
            )
            return self._fallback_fetch(request)

        items = list(payload.get(series_key, {}).items())
        items.sort(reverse=True)
        if request.limit:
            items = items[: int(request.limit)]

        bars = Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
        for ts_str, entry in items:
            try:
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
            except ValueError:
                logger.debug(
                    "AlphaVantage daily timestamp parse failed symbol=%s ts=%s",
                    request.symbol,
                    ts_str,
                )
                continue
            bars.append(
                Bar(
                    symbol=request.symbol.upper(),
                    vendor=self.name,
                    timestamp=ts,
                    open=float(entry.get("1. open", 0.0)),
                    high=float(entry.get("2. high", 0.0)),
                    low=float(entry.get("3. low", 0.0)),
                    close=float(entry.get("4. close", 0.0)),
                    volume=float(entry.get("6. volume", entry.get("5. volume", 0.0))),
                    timezone="UTC",
                    source="daily_adjusted",
                )
            )
        if bars.data:
            return bars
        return self._fallback_fetch(request)

    def _fallback_fetch(self, request: FetchRequest) -> Bars:
        for vendor in self._fallback_vendors:
            try:
                fallback = vendor.fetch_bars(request)
            except Exception as exc:  # pragma: no cover - optional fallback failures
                logger.debug(
                    "AlphaVantage daily fallback via %s failed symbol=%s err=%s",
                    getattr(vendor, "name", type(vendor).__name__),
                    request.symbol,
                    exc,
                )
                continue
            if fallback.data:
                logger.info(
                    "AlphaVantage daily fallback succeeded via %s for symbol=%s",
                    getattr(vendor, "name", type(vendor).__name__),
                    request.symbol,
                )
                return fallback

        return Bars(symbol=request.symbol.upper(), vendor=self.name, timezone="UTC")
