from __future__ import annotations

from typing import Dict, Iterable, Optional, Sequence, Tuple

from loguru import logger

from app.dal.manager import MarketDataDAL
from app.dal.schemas import Bar

DEFAULT_INTRADAY_VENDORS: Sequence[str] = (
    "alpaca",
    "finnhub",
    "twelvedata",
    "yahoo",
)


def fetch_latest_bar(
    dal: MarketDataDAL,
    symbol: str,
    *,
    interval: str = "1Min",
    vendors: Sequence[str] = DEFAULT_INTRADAY_VENDORS,
) -> Tuple[Optional[Bar], Optional[str]]:
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None, None
    for vendor in vendors:
        try:
            batch = dal.fetch_bars(symbol, interval=interval, vendor=vendor, limit=1)
        except Exception as exc:  # pragma: no cover - network/transient failures
            logger.debug(
                "latest bar fetch failed vendor={} symbol={} error={}",
                vendor,
                symbol,
                exc,
            )
            continue
        data = batch.bars.data
        if data:
            return data[-1], vendor
    return None, None


def batch_latest_close(
    dal: MarketDataDAL,
    symbols: Iterable[str],
    *,
    vendor: str = "yahoo",
    limit: int = 1,
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for sym in {s.strip().upper() for s in symbols if s and s.strip()}:
        try:
            batch = dal.fetch_bars(sym, interval="1Day", vendor=vendor, limit=limit)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug(
                "latest close fetch failed vendor={} symbol={} error={}",
                vendor,
                sym,
                exc,
            )
            continue
        data = batch.bars.data
        if not data:
            continue
        last = data[-1].close
        if last and float(last) > 0:
            out[sym] = float(last)
    return out


def batch_latest_volume(
    dal: MarketDataDAL,
    symbols: Iterable[str],
    *,
    interval: str = "1Min",
    vendors: Sequence[str] = DEFAULT_INTRADAY_VENDORS,
) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for sym in {s.strip().upper() for s in symbols if s and s.strip()}:
        bar, _ = fetch_latest_bar(dal, sym, interval=interval, vendors=vendors)
        if bar and bar.volume:
            out[sym] = int(bar.volume)
    return out


__all__ = [
    "DEFAULT_INTRADAY_VENDORS",
    "batch_latest_close",
    "batch_latest_volume",
    "fetch_latest_bar",
]
