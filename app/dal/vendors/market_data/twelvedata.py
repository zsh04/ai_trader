from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger

from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient
from app.utils import env as ENV
from app.utils.http import http_get


class TwelveDataVendor(VendorClient):
    """Twelve Data time-series client."""

    BASE_URL = "https://api.twelvedata.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timezone_name: str = "UTC",
    ) -> None:
        super().__init__("twelvedata")
        self.api_key = (
            api_key
            or os.getenv("TWELVEDATA_API_KEY")
            or getattr(ENV, "TWELVEDATA_API_KEY", "")
        )
        self.base_url = base_url.rstrip("/")
        self.timezone_name = timezone_name

    def fetch_bars(self, request: FetchRequest) -> Bars:
        symbol = request.symbol.upper()
        bars = Bars(symbol=symbol, vendor=self.name, timezone=self.timezone_name)
        if not self.api_key:
            logger.debug("twelvedata vendor missing API key; returning empty bars")
            return bars

        interval = _map_interval(request.interval)
        params: Dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "apikey": self.api_key,
            "format": "JSON",
        }

        if request.limit:
            params["outputsize"] = int(request.limit)
        if request.start:
            params["start_date"] = _format_timestamp(request.start)
        if request.end:
            params["end_date"] = _format_timestamp(request.end)

        status, payload = http_get(
            f"{self.base_url}/time_series",
            params=params,
            timeout=ENV.HTTP_TIMEOUT,
            retries=ENV.HTTP_RETRIES,
            backoff=ENV.HTTP_BACKOFF,
        )

        if status != 200:
            logger.debug(
                "twelvedata fetch failed status={} symbol={} payload={}",
                status,
                symbol,
                (payload or {}).get("message"),
            )
            return bars

        values = (payload or {}).get("values") or []
        if not isinstance(values, list) or not values:
            return bars

        # Twelve Data returns newest first; reverse for chronological order
        for entry in reversed(values):
            ts = _parse_datetime(entry.get("datetime"))
            if ts is None:
                continue
            bars.append(
                Bar(
                    symbol=symbol,
                    vendor=self.name,
                    timestamp=ts,
                    open=_safe_float(entry.get("open")),
                    high=_safe_float(entry.get("high")),
                    low=_safe_float(entry.get("low")),
                    close=_safe_float(entry.get("close")) or 0.0,
                    volume=_safe_float(entry.get("volume"), allow_zero=True) or 0.0,
                    timezone=self.timezone_name,
                    source="historical",
                )
            )

        return bars


def _map_interval(interval: Optional[str]) -> str:
    if not interval:
        return "1day"
    lookup = {
        "1Min": "1min",
        "1min": "1min",
        "1m": "1min",
        "5Min": "5min",
        "5m": "5min",
        "15Min": "15min",
        "15m": "15min",
        "30Min": "30min",
        "30m": "30min",
        "1Hour": "1h",
        "1H": "1h",
        "60m": "1h",
        "1Day": "1day",
        "1D": "1day",
        "1day": "1day",
    }
    return lookup.get(interval, "1day")


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        candidate = str(value).replace("T", " ")
        dt = datetime.fromisoformat(candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _safe_float(value: Any, *, allow_zero: bool = False) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not allow_zero and num == 0.0:
        return None
    return num


__all__ = ["TwelveDataVendor"]
