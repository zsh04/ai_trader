from __future__ import annotations

import importlib
import logging
import time
from datetime import datetime
from typing import Dict, List

import pandas as pd
import yfinance as yf

from app.utils.env import YF_ENABLED

log = logging.getLogger(__name__)
_CHUNK_SIZE = 25
_RETRY_COUNT = 3
_RETRY_DELAY = 2.0


def _yf():
    try:
        return importlib.import_module("yfinance")
    except Exception as e:
        log.debug("yfinance not available: %s", e)
        return None


def _chunk(symbols: List[str], n=_CHUNK_SIZE) -> List[List[str]]:
    syms = [s.strip().upper() for s in symbols if s and s.strip()]
    return [syms[i : i + n] for i in range(0, len(syms), n)]


def _retry_yf(func, *args, **kwargs):
    for attempt in range(_RETRY_COUNT):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log.debug("yfinance transient error attempt %s: %s", attempt + 1, e)
            time.sleep(_RETRY_DELAY * (attempt + 1))
    return None


def intraday_last(symbols: List[str]) -> Dict[str, float]:
    if not YF_ENABLED or not symbols:
        return {}
    yf = _yf()
    if not yf:
        return {}
    out: Dict[str, float] = {}
    for batch in _chunk(symbols):
        for s in batch:
            try:
                tk = yf.Ticker(s)
                hist = _retry_yf(tk.history, period="1d", interval="1m", prepost=True)
                if (hist is None or len(hist) == 0) and hist is not None:
                    hist = _retry_yf(
                        tk.history, period="5d", interval="1d", prepost=True
                    )
                if hist is not None and len(hist) > 0:
                    out[s.upper()] = float(hist["Close"].iloc[-1])
            except Exception as e:
                log.debug("yf intraday error %s: %s", s, e)
    return out


def latest_close(symbols: List[str]) -> Dict[str, float]:
    if not YF_ENABLED or not symbols:
        return {}
    yf = _yf()
    if not yf:
        return {}
    out: Dict[str, float] = {}
    for batch in _chunk(symbols):
        for s in batch:
            try:
                tk = yf.Ticker(s)
                val = None
                fi = getattr(tk, "fast_info", None)
                if isinstance(fi, dict):
                    val = (
                        fi.get("previous_close")
                        or fi.get("last_close")
                        or fi.get("last_price")
                    )
                if val is None:
                    hist = _retry_yf(
                        tk.history, period="5d", interval="1d", prepost=True
                    )
                    if hist is not None and len(hist) > 0:
                        val = float(hist["Close"].iloc[-1])
                if val and float(val) > 0:
                    out[s.upper()] = float(val)
            except Exception as e:
                log.debug("yf latest_close error %s: %s", s, e)
    return out


def latest_volume(symbols: List[str]) -> Dict[str, int]:
    if not YF_ENABLED or not symbols:
        return {}
    yf = _yf()
    if not yf:
        return {}
    out: Dict[str, int] = {}
    for batch in _chunk(symbols):
        for s in batch:
            try:
                tk = yf.Ticker(s)
                hist = _retry_yf(tk.history, period="5d", interval="1d", prepost=True)
                if hist is not None and len(hist) > 0 and "Volume" in hist.columns:
                    v = int(hist["Volume"].iloc[-1])
                    if v > 0:
                        out[s.upper()] = v
            except Exception as e:
                log.debug("yf latest_volume error %s: %s", s, e)
    return out


def get_history_daily(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """
    Download daily OHLCV data for a symbol from Yahoo Finance.
    Returns a DataFrame with columns: open, high, low, close, volume
    and a DatetimeIndex in UTC.
    """
    df = yf.download(
        symbol, start=start, end=end, progress=False, interval="1d", auto_adjust=False
    )
    if df.empty:
        raise ValueError(f"No data returned for {symbol} from {start} to {end}")

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    return df
