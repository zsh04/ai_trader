from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
import requests
from loguru import logger

from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient
from app.utils import env as ENV


class MarketstackVendor(VendorClient):
    """
    Marketstack implementation using the EOD endpoint.
    Docs: https://marketstack.com/documentation
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("marketstack")
        self.api_key = (
            api_key
            or requests.utils.quote(ENV.MARKETSTACK_API_KEY)
            if ENV.MARKETSTACK_API_KEY
            else ""
        )
        self.base_url = "http://api.marketstack.com/v1"

    def fetch_bars(self, request: FetchRequest) -> Bars:
        if not self.api_key:
            logger.warning("Marketstack API key missing; returning empty bars.")
            return Bars(
                symbol=request.symbol,
                vendor=self.name,
                interval=request.interval,
                data=[],
            )

        # Marketstack EOD only supports decent daily data on the free/basic tiers
        # We'll map "1Day" -> "eod" endpoint
        if request.interval != "1Day":
            logger.warning(
                "Marketstack vendor currently only optimized for 1Day (EOD). Requested: {}",
                request.interval,
            )

        url = f"{self.base_url}/eod"
        params: Dict[str, Any] = {
            "access_key": self.api_key,
            "symbols": request.symbol,
            "limit": request.limit or 1000,
        }

        if request.start:
            params["date_from"] = request.start.strftime("%Y-%m-%d")
        if request.end:
            params["date_to"] = request.end.strftime("%Y-%m-%d")

        try:
            resp = requests.get(url, params=params, timeout=ENV.HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("Marketstack fetch failed: {}", exc)
            return Bars(
                symbol=request.symbol,
                vendor=self.name,
                interval=request.interval,
                data=[],
            )

        error = data.get("error")
        if error:
            logger.error("Marketstack API error: {}", error)
            return Bars(
                symbol=request.symbol,
                vendor=self.name,
                interval=request.interval,
                data=[],
            )

        # Response structure: {"data": [...], "pagination": {...}}
        records = data.get("data", [])
        bars = []
        for r in records:
            # Marketstack returns date like "2023-01-01T00:00:00+0000"
            try:
                # simple parse
                dt = pd.to_datetime(r.get("date"))
                bars.append(
                    Bar(
                        symbol=request.symbol,
                        vendor=self.name,
                        timestamp=dt,
                        open=float(r.get("open") or 0.0),
                        high=float(r.get("high") or 0.0),
                        low=float(r.get("low") or 0.0),
                        close=float(r.get("close") or 0.0),
                        volume=float(r.get("volume") or 0.0),
                    )
                )
            except Exception:
                continue

        # Marketstack returns newest first usually; DAL expects oldest first or doesn't care?
        # Standardizing on oldest->newest is usually safe for backtest engines.
        bars.sort(key=lambda x: x.timestamp)

        return Bars(
            symbol=request.symbol,
            vendor=self.name,
            interval=request.interval,
            data=bars,
        )
