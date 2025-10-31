from __future__ import annotations

import re
from dataclasses import is_dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


def _normalize_name(s: str) -> str:
    """
    Normalizes a string by converting it to lowercase and replacing whitespace and hyphens with underscores.

    Args:
        s (str): The string to normalize.

    Returns:
        str: The normalized string.
    """
    return re.sub(r"[\s\-]+", "_", s).lower()


def get_param(p: Any, key: str, default: Any) -> Any:
    """
    Gets a parameter from a dictionary or dataclass.

    Args:
        p (Any): The dictionary or dataclass.
        key (str): The key to get.
        default (Any): The default value to return if the key is not found.

    Returns:
        Any: The value of the parameter.
    """
    if isinstance(p, Mapping):
        return p.get(key, default)
    if is_dataclass(p):
        return getattr(p, key, default)
    return getattr(p, key, default)


def as_series(obj: Any) -> pd.Series:
    """
    Converts an object to a pandas Series.

    Args:
        obj (Any): The object to convert.

    Returns:
        pd.Series: The converted Series.
    """
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0]
    return obj


def first_column(df: pd.DataFrame, name: str) -> pd.Series:
    """
    Selects the first column with a given name.

    Args:
        df (pd.DataFrame): The DataFrame to select from.
        name (str): The name of the column to select.

    Returns:
        pd.Series: The selected column.
    """
    obj = df.loc[:, name]
    if isinstance(obj, pd.DataFrame):
        obj = obj.iloc[:, 0]
    return obj


def pick_col(df: pd.DataFrame, *candidates: str) -> pd.Series:
    """
    Picks a column from a DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to pick from.
        *candidates (str): A list of candidate column names.

    Returns:
        pd.Series: The picked column.
    """
    if df is None or df.empty:
        raise KeyError("Empty DataFrame")

    cols = list(df.columns)
    lower_map = {_normalize_name(c): c for c in cols}

    for name in candidates:
        if name in df.columns:
            return first_column(df, name)

    for name in candidates:
        key = _normalize_name(name)
        if key in lower_map:
            return first_column(df, lower_map[key])

    for name in candidates:
        key = _normalize_name(name)
        for c in cols:
            cc = _normalize_name(c)
            if (
                cc == key
                or cc.startswith(key + "_")
                or cc.endswith("_" + key)
                or key in cc
            ):
                return first_column(df, c)

    raise KeyError(
        f"None of {candidates} found in DataFrame. "
        f"Available: {cols[:12]}{'...' if len(cols) > 12 else ''}"
    )


def ensure_flat_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures that a DataFrame has a flat, lowercase, and deduplicated column index.

    Args:
        df (pd.DataFrame): The DataFrame to process.

    Returns:
        pd.DataFrame: The processed DataFrame.
    """
    out = df.copy().sort_index()
    cols = out.columns

    try:
        if isinstance(cols, pd.MultiIndex):
            flat: list[str] = []
            for tup in cols.to_list():
                if not isinstance(tup, (tuple, list)):
                    tup = (tup,)
                parts: list[str] = []
                for x in tup:
                    sx = "" if x is None else str(x)
                    sx = sx.strip()
                    if sx:
                        parts.append(sx)
                flat.append("_".join(parts))
            out.columns = pd.Index([s.lower() for s in flat])
        else:
            out.columns = pd.Index([str(c).strip().lower() for c in cols])
    except Exception:
        out.columns = pd.Index([str(c).strip().lower() for c in out.columns])

    out = out.loc[:, ~out.columns.duplicated(keep="first")]
    return out


def ema(series: pd.Series, span: int) -> pd.Series:
    """
    Calculates the exponential moving average of a Series.

    Args:
        series (pd.Series): The Series to calculate the EMA of.
        span (int): The span of the EMA.

    Returns:
        pd.Series: The EMA of the Series.
    """
    return as_series(series).ewm(span=span, adjust=False).mean()


def rolling_max(series: pd.Series, n: int, min_periods: int | None = None) -> pd.Series:
    """
    Calculates the rolling maximum of a Series.

    Args:
        series (pd.Series): The Series to calculate the rolling maximum of.
        n (int): The window size.
        min_periods (int | None): The minimum number of periods.

    Returns:
        pd.Series: The rolling maximum of the Series.
    """
    mp = n if min_periods is None else min_periods
    return as_series(series).rolling(n, min_periods=mp).max()


def rolling_min(series: pd.Series, n: int, min_periods: int | None = None) -> pd.Series:
    """
    Calculates the rolling minimum of a Series.

    Args:
        series (pd.Series): The Series to calculate the rolling minimum of.
        n (int): The window size.
        min_periods (int | None): The minimum number of periods.

    Returns:
        pd.Series: The rolling minimum of the Series.
    """
    mp = n if min_periods is None else min_periods
    return as_series(series).rolling(n, min_periods=mp).min()


def safe_atr(df: pd.DataFrame, n: int) -> pd.Series:
    """
    Calculates the Average True Range (ATR) of a DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to calculate the ATR of.
        n (int): The window size.

    Returns:
        pd.Series: The ATR of the DataFrame.
    """
    high = pick_col(df, "high", "ohlc_high", "h")
    low = pick_col(df, "low", "ohlc_low", "l")
    close = pick_col(df, "close", "adj_close", "close_price", "c", "ohlc_close")
    prev_c = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_c).abs(), (low - prev_c).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(n, min_periods=n).mean()

    atr = atr.replace([np.inf, -np.inf], np.nan).bfill().ffill()
    atr = atr.where(atr > 0, atr.rolling(5, min_periods=1).mean())
    med = float(atr.median()) if not np.isnan(atr.median()) else 1e-6
    atr = atr.fillna(med).clip(lower=1e-6)
    return atr


def rank_percentile(series: pd.Series, window: int) -> pd.Series:
    """
    Calculates the rolling percentile rank of a Series.

    Args:
        series (pd.Series): The Series to calculate the rolling percentile rank of.
        window (int): The window size.

    Returns:
        pd.Series: The rolling percentile rank of the Series.
    """
    s = as_series(series)

    def _pct_rank(x: pd.Series) -> float:
        last = x.iloc[-1]
        return float((x <= last).mean())

    return s.rolling(window, min_periods=window).apply(_pct_rank, raw=False)
