from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_COL_ALIASES = {
    "open": "o",
    "o": "o",
    "high": "h",
    "h": "h",
    "low": "lo",
    "l": "lo",
    "lo": "lo",
    "close": "c",
    "c": "c",
    "adj_close": "c",
    "volume": "v",
    "v": "v",
}


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardizes the column names of a DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to standardize.

    Returns:
        pd.DataFrame: A new DataFrame with standardized column names.
    """
    mapping = {col: _COL_ALIASES.get(str(col).lower(), col) for col in df.columns}
    out = df.rename(columns=mapping).copy()
    return out


def aggregate_ohlcv(
    df: pd.DataFrame,
    rule: str,
    *,
    tz: Optional[str] = None,
    label: str = "right",
    closed: str = "right",
) -> pd.DataFrame:
    """
    Aggregates OHLCV data to a higher timeframe.

    Args:
        df (pd.DataFrame): A DataFrame with OHLCV data.
        rule (str): The resampling rule.
        tz (Optional[str]): The timezone to use.
        label (str): The label for the resampled data.
        closed (str): The closed side for the resampled data.

    Returns:
        pd.DataFrame: An aggregated DataFrame.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("aggregate_ohlcv expects a DataFrame indexed by DatetimeIndex")

    df_std = _standardize_columns(df)

    idx = df_std.index
    if tz:
        if idx.tz is None:
            df_std = df_std.tz_localize(
                tz, nonexistent="shift_forward", ambiguous="NaT"
            )
        else:
            df_std = df_std.tz_convert(tz)

    agg = {
        "o": "first",
        "h": "max",
        "lo": "min",
        "c": "last",
        "v": "sum",
    }

    available = {k: v for k, v in agg.items() if k in df_std.columns}
    res = df_std.resample(rule, label=label, closed=closed).agg(available)

    res = res.dropna(how="all")
    return res


def mtf_aggregate(
    df: pd.DataFrame,
    rules: Iterable[str] = ("5min", "15min", "1H", "1D"),
    *,
    tz: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Aggregates a DataFrame into multiple timeframes.

    Args:
        df (pd.DataFrame): The DataFrame to aggregate.
        rules (Iterable[str]): A list of resampling rules.
        tz (Optional[str]): The timezone to use.

    Returns:
        Dict[str, pd.DataFrame]: A dictionary of aggregated DataFrames.
    """
    out: Dict[str, pd.DataFrame] = {}
    for rule in rules:
        try:
            out[rule] = aggregate_ohlcv(df, rule, tz=tz)
        except Exception as e:
            log.warning("mtf_aggregate: failed rule=%s err=%s", rule, e)
    return out


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Computes the Relative Strength Index (RSI).

    Args:
        series (pd.Series): A Series of price data.
        period (int): The lookback period for the RSI.

    Returns:
        pd.Series: A Series of RSI values.
    """
    s = pd.Series(series).astype(float)
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    alpha = 1.0 / float(period)
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(method="bfill")


def mtf_rsi(
    closes_by_tf: Mapping[str, pd.Series],
    period: int = 14,
    suffix: str = "rsi",
) -> pd.DataFrame:
    """
    Computes the RSI for multiple timeframes.

    Args:
        closes_by_tf (Mapping[str, pd.Series]): A mapping of timeframes to close prices.
        period (int): The lookback period for the RSI.
        suffix (str): The suffix for the RSI column.

    Returns:
        pd.DataFrame: A DataFrame with the RSI values for each timeframe.
    """
    frames: List[pd.DataFrame] = []
    for tf, ser in closes_by_tf.items():
        try:
            ser = pd.Series(ser).astype(float)
            out = rsi(ser, period=period).to_frame(name=f"{suffix}@{tf}")
            frames.append(out)
        except Exception as e:
            log.warning("mtf_rsi: failed timeframe=%s err=%s", tf, e)
    if not frames:
        return pd.DataFrame()
    wide = pd.concat(frames, axis=1).sort_index()
    return wide.ffill()


def build_mtf_features(
    df_1m: pd.DataFrame,
    rules: Iterable[str] = ("5min", "15min", "1H", "1D"),
    *,
    tz: Optional[str] = None,
    include_prices: bool = True,
    rsi_period: Optional[int] = 14,
) -> pd.DataFrame:
    """
    Builds a wide feature table by aggregating OHLCV and computing RSI per timeframe.

    Args:
        df_1m (pd.DataFrame): A DataFrame with 1-minute OHLCV data.
        rules (Iterable[str]): A list of resampling rules.
        tz (Optional[str]): The timezone to use.
        include_prices (bool): Whether to include prices in the output.
        rsi_period (Optional[int]): The lookback period for the RSI.

    Returns:
        pd.DataFrame: A wide DataFrame with the computed features.
    """
    buckets = mtf_aggregate(df_1m, rules, tz=tz)

    frames: List[pd.DataFrame] = []

    if include_prices:
        for tf, bar in buckets.items():
            part = bar[
                [c for c in ["o", "h", "lo", "c", "v"] if c in bar.columns]
            ].copy()
            part = part.add_suffix(f"@{tf}")
            frames.append(part)

    if rsi_period is not None:
        closes = {tf: bar["c"] for tf, bar in buckets.items() if "c" in bar.columns}
        if closes:
            frames.append(mtf_rsi(closes, period=rsi_period, suffix="rsi"))

    if not frames:
        return pd.DataFrame()

    wide = pd.concat(frames, axis=1).sort_index()
    return wide
