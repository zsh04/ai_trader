"""
Feature engineering: technical indicators.

Contains vectorized indicator calculations built on pandas.
Designed for extensibility and unit testing.
"""

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute Relative Strength Index (RSI).

    Parameters
    ----------
    series : pd.Series
        Price series (e.g., closing prices).
    period : int, default 14
        Lookback period for RSI.

    Returns
    -------
    pd.Series
        RSI values scaled 0–100.
    """
    if series is None or len(series) < period:
        log.warning(
            "RSI input too short (len=%s < period=%s)",
            len(series) if series is not None else None,
            period,
        )
        return pd.Series(dtype=float)

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.fillna(method="bfill").clip(0, 100)

    log.debug("RSI computed for %d bars", len(series))
    return rsi_val


def sma(series: pd.Series, period: int = 20) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=1).mean()


def ema(series: pd.Series, period: int = 20) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range using OHLC data.
    Requires columns: 'high', 'low', 'close'.
    """
    if not all(c in df.columns for c in ["high", "low", "close"]):
        raise ValueError("DataFrame must contain columns: high, low, close")
    tr = df[["high", "low", "close"]].copy()
    tr["h-l"] = tr["high"] - tr["low"]
    tr["h-cp"] = (tr["high"] - tr["close"].shift()).abs()
    tr["l-cp"] = (tr["low"] - tr["close"].shift()).abs()
    tr["tr"] = tr[["h-l", "h-cp", "l-cp"]].max(axis=1)
    return tr["tr"].ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


__all__ = ["rsi", "sma", "ema", "atr"]
