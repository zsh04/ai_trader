from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence

import pandas as pd


@dataclass(frozen=True, slots=True)
class Bar:
    """Normalized OHLCV bar."""

    symbol: str
    vendor: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timezone: str = "UTC"
    source: str = "historical"

    def as_dict(self) -> dict:
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return {
            "symbol": self.symbol,
            "vendor": self.vendor,
            "timestamp": ts.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "timezone": self.timezone,
            "source": self.source,
        }


@dataclass(slots=True)
class Bars:
    """Collection of bars for a single symbol."""

    symbol: str
    vendor: str
    timezone: str
    data: List[Bar] = field(default_factory=list)

    def append(self, bar: Bar) -> None:
        if bar.symbol != self.symbol:
            raise ValueError("bar symbol mismatch")
        self.data.append(bar)

    def extend(self, bars: Iterable[Bar]) -> None:
        for bar in bars:
            self.append(bar)

    def to_dicts(self) -> List[dict]:
        return [bar.as_dict() for bar in self.data]

    def to_dataframe(self) -> pd.DataFrame:
        if not self.data:
            return pd.DataFrame(
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            )
        raw = [
            {
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in self.data
        ]
        df = pd.DataFrame(raw).set_index("timestamp").sort_index()
        if self.timezone:
            df.index = df.index.tz_convert(self.timezone)
        return df


@dataclass(frozen=True, slots=True)
class SignalFrame:
    """Kalman-derived probabilistic snapshot."""

    symbol: str
    vendor: str
    timestamp: datetime
    price: float
    volume: float
    filtered_price: float
    velocity: float
    uncertainty: float
    butterworth_price: Optional[float] = None
    ema_price: Optional[float] = None

    def as_dict(self) -> dict:
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return {
            "symbol": self.symbol,
            "vendor": self.vendor,
            "timestamp": ts.isoformat(),
            "price": self.price,
            "volume": self.volume,
            "filtered_price": self.filtered_price,
            "velocity": self.velocity,
            "uncertainty": self.uncertainty,
            "butterworth_price": self.butterworth_price,
            "ema_price": self.ema_price,
        }


def merge_bars(symbol: str, vendor: str, timezone_name: str, series: Sequence[dict]) -> Bars:
    """Utility to construct a Bars object from raw dict sequences."""
    out = Bars(symbol=symbol, vendor=vendor, timezone=timezone_name)
    for payload in series:
        ts = payload.get("timestamp") or payload.get("time")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        elif not isinstance(ts, datetime):
            continue
        bar = Bar(
            symbol=symbol,
            vendor=vendor,
            timestamp=ts.astimezone(timezone.utc),
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=float(payload.get("volume") or payload.get("vol") or 0.0),
            timezone=timezone_name,
            source=str(payload.get("source") or "historical"),
        )
        out.append(bar)
    return out


__all__ = ["Bar", "Bars", "SignalFrame", "merge_bars"]
