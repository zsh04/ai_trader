from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
from loguru import logger

from app.agent.probabilistic.regime import RegimeSnapshot
from app.dal.schemas import Bar, Bars, SignalFrame


def store_bars_to_parquet(bars: Bars, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / f"{bars.symbol}_{bars.vendor}.parquet"
    df = bars.to_dataframe()
    df.to_parquet(file_path, index=True)
    logger.debug("stored bars to {} rows={} symbol={} vendor={}", file_path, len(df), bars.symbol, bars.vendor)
    return file_path


def load_bars_from_parquet(path: Path, symbol: str, vendor: str, timezone: str = "UTC") -> Bars:
    df = pd.read_parquet(path)
    index = pd.to_datetime(df.index)
    if index.tz is None:  # type: ignore[attr-defined]
        index = index.tz_localize("UTC")
    df.index = index.tz_convert(timezone)
    out = Bars(symbol=symbol, vendor=vendor, timezone=timezone)
    for ts, row in df.sort_index().iterrows():
        out.append(
            Bar(
                symbol=symbol,
                vendor=vendor,
                timestamp=ts.to_pydatetime(),
                open=float(row.get("open", 0.0)),
                high=float(row.get("high", 0.0)),
                low=float(row.get("low", 0.0)),
                close=float(row.get("close", 0.0)),
                volume=float(row.get("volume", 0.0)),
                timezone=timezone,
                source="cache",
            )
        )
    return out


def store_signals_to_parquet(signals: Iterable[SignalFrame], directory: Path) -> Optional[Path]:
    signals_list = list(signals)
    if not signals_list:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    key = f"{signals_list[0].symbol}_{signals_list[0].vendor}_signals.parquet"
    file_path = directory / key
    df = pd.DataFrame(
        [
            {
                "timestamp": frame.timestamp,
                "price": frame.price,
                "volume": frame.volume,
                "filtered_price": frame.filtered_price,
                "velocity": frame.velocity,
                "uncertainty": frame.uncertainty,
                "butterworth_price": frame.butterworth_price,
                "ema_price": frame.ema_price,
            }
            for frame in signals_list
        ]
    ).set_index("timestamp")
    df.to_parquet(file_path, index=True)
    logger.debug(
        "stored signal frames to {} rows={} symbol={} vendor={}",
        file_path,
        len(df),
        signals_list[0].symbol,
        signals_list[0].vendor,
    )
    return file_path


def store_regimes_to_parquet(regimes: Iterable[RegimeSnapshot], directory: Path) -> Optional[Path]:
    regime_list = list(regimes)
    if not regime_list:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    key = f"{regime_list[0].symbol}_regimes.parquet"
    file_path = directory / key
    df = pd.DataFrame(
        [
            {
                "timestamp": snapshot.timestamp,
                "regime": snapshot.regime,
                "volatility": snapshot.volatility,
                "uncertainty": snapshot.uncertainty,
                "momentum": snapshot.momentum,
            }
            for snapshot in regime_list
        ]
    ).set_index("timestamp")
    df.to_parquet(file_path, index=True)
    logger.debug(
        "stored regime snapshots to {} rows={} symbol={}",
        file_path,
        len(df),
        regime_list[0].symbol,
    )
    return file_path
