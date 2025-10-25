from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# Column normalization
# --------------------------------------------------------------------------------------

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
    """Return a copy of *df* with columns renamed to canonical short form.

    Supported inputs: open/high/low/close/volume, o/h/l/lo/c/v, adj_close.
    Extra columns are preserved as-is.
    """
    mapping = {col: _COL_ALIASES.get(str(col).lower(), col) for col in df.columns}
    out = df.rename(columns=mapping).copy()
    return out


# --------------------------------------------------------------------------------------
# Resampling / aggregation
# --------------------------------------------------------------------------------------

def aggregate_ohlcv(
    df: pd.DataFrame,
    rule: str,
    *,
    tz: Optional[str] = None,
    label: str = "right",
    closed: str = "right",
) -> pd.DataFrame:
    """Aggregate intraday OHLCV to a higher timeframe using pandas resample.

    Parameters
    ----------
    df : DataFrame with DateTimeIndex and columns including o,h,lo,c,v (aliases ok)
    rule : pandas offset alias (e.g. '5min', '15min', '1H', '1D')
    tz : ensure index is tz-aware in this timezone if provided (no conversion if already tz-aware)
    label/closed : forwarded to `resample()` to use right-edge semantics (typical for markets)
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("aggregate_ohlcv expects a DataFrame indexed by DatetimeIndex")

    df_std = _standardize_columns(df)

    # Ensure tz-awareness if requested
    idx = df_std.index
    if tz:
        if idx.tz is None:
            df_std = df_std.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
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
    res = (
        df_std.resample(rule, label=label, closed=closed).agg(available)
    )

    # Drop empty bars (can happen at session boundaries)
    res = res.dropna(how="all")
    return res


def mtf_aggregate(
    df: pd.DataFrame,
    rules: Iterable[str] = ("5min", "15min", "1H", "1D"),
    *,
    tz: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """Aggregate *df* into multiple timeframes and return a dict {rule: DataFrame}."""
    out: Dict[str, pd.DataFrame] = {}
    for rule in rules:
        try:
            out[rule] = aggregate_ohlcv(df, rule, tz=tz)
        except Exception as e:
            log.warning("mtf_aggregate: failed rule=%s err=%s", rule, e)
    return out


# --------------------------------------------------------------------------------------
# Basic RSI (EMA/ Wilder style) so we don't depend on external TA libs
# --------------------------------------------------------------------------------------

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI on a price series using Wilder's smoothing via EMA.

    Returns a Series aligned to the input index with float values in [0, 100].
    """
    s = pd.Series(series).astype(float)
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing via EMA(alpha=1/period)
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
    """Compute RSI per timeframe and return a wide DataFrame with suffixed columns.

    Parameters
    ----------
    closes_by_tf : mapping like {"5min": close_series, "15min": close_series, ...}
    period : RSI period per timeframe
    suffix : column name prefix (defaults to 'rsi')
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
    # Outer-join on the union of timestamps, forward-fill to align views
    wide = pd.concat(frames, axis=1).sort_index()
    return wide.ffill()


# --------------------------------------------------------------------------------------
# Convenience: build a single wide feature table
# --------------------------------------------------------------------------------------

def build_mtf_features(
    df_1m: pd.DataFrame,
    rules: Iterable[str] = ("5min", "15min", "1H", "1D"),
    *,
    tz: Optional[str] = None,
    include_prices: bool = True,
    rsi_period: Optional[int] = 14,
) -> pd.DataFrame:
    """Create a wide feature table by aggregating OHLCV and computing RSI per timeframe.

    The result includes columns like `c@5min`, `v@1H`, and optionally `rsi@15min`.
    """
    buckets = mtf_aggregate(df_1m, rules, tz=tz)

    frames: List[pd.DataFrame] = []

    # Prices & volumes per timeframe
    if include_prices:
        for tf, bar in buckets.items():
            part = bar[[c for c in ["o", "h", "lo", "c", "v"] if c in bar.columns]].copy()
            part = part.add_suffix(f"@{tf}")
            frames.append(part)

    # RSI per timeframe (based on close)
    if rsi_period is not None:
        closes = {tf: bar["c"] for tf, bar in buckets.items() if "c" in bar.columns}
        if closes:
            frames.append(mtf_rsi(closes, period=rsi_period, suffix="rsi"))

    if not frames:
        return pd.DataFrame()

    wide = pd.concat(frames, axis=1).sort_index()
    return wide
