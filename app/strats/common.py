from __future__ import annotations

import re
from dataclasses import is_dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


def _normalize_name(s: str) -> str:
    return re.sub(r"[\s\-]+", "_", s).lower()


# -------- Param helpers --------
def get_param(p: Any, key: str, default: Any) -> Any:
    """Read a parameter from either a dict or a dataclass; fallback to default."""
    if isinstance(p, Mapping):
        return p.get(key, default)
    if is_dataclass(p):
        return getattr(p, key, default)
    return getattr(p, key, default)


# -------- Series/DataFrame safety --------
def as_series(obj: Any) -> pd.Series:
    """Coerce single-column DataFrames to Series; pass Series through."""
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0]
    return obj


def first_column(df: pd.DataFrame, name: str) -> pd.Series:
    """
    Return a Series for the given column even if duplicates exist
    (DataFrame would be returned otherwise).
    """
    obj = df.loc[:, name]
    if isinstance(obj, pd.DataFrame):
        obj = obj.iloc[:, 0]
    return obj


def pick_col(df: pd.DataFrame, *candidates: str) -> pd.Series:
    """
    Return the first matching column (case-insensitive, with basic normalization).
    Tries exact, case-insensitive exact, then fuzzy (prefix/suffix/contains).
    """
    if df is None or df.empty:
        raise KeyError("Empty DataFrame")

    cols = list(df.columns)
    lower_map = {_normalize_name(c): c for c in cols}

    # 1) Exact (as-is)
    for name in candidates:
        if name in df.columns:
            return first_column(df, name)

    # 2) Exact (normalized, case-insensitive)
    for name in candidates:
        key = _normalize_name(name)
        if key in lower_map:
            return first_column(df, lower_map[key])

    # 3) Fuzzy (contains/prefix/suffix) with normalization
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
    - Sort index
    - Flatten MultiIndex columns (if present)
    - Lowercase col names
    - Drop duplicate columns (keep first)
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


def choose_probabilistic_price(df: pd.DataFrame) -> pd.Series:
    """Prefer probabilistic filtered price columns when available."""
    for col in (
        "prob_filtered_price",
        "filtered_price",
        "prob_price",
        "prob_butterworth_price",
    ):
        if col in df.columns:
            series = as_series(df[col])
            if series.notna().any():
                return series.astype(float)
    return pick_col(df, "close", "adj_close", "close_price", "c", "ohlc_close")


def probabilistic_velocity_gate(df: pd.DataFrame, threshold: float) -> pd.Series:
    vel = None
    for col in ("prob_velocity", "velocity"):
        if col in df.columns:
            vel = as_series(df[col])
            break
    if vel is None:
        return pd.Series(True, index=df.index)
    return vel.fillna(0.0) >= threshold


def probabilistic_regime_gate(
    df: pd.DataFrame, whitelist: Sequence[str] | None
) -> pd.Series:
    if "regime_label" not in df.columns or not whitelist:
        return pd.Series(True, index=df.index)
    allowed = {str(item).lower() for item in whitelist if str(item).strip()}
    if not allowed:
        return pd.Series(True, index=df.index)
    regimes = as_series(df["regime_label"]).astype(str).str.lower()
    return regimes.isin(allowed)


# -------- Math helpers --------
def ema(series: pd.Series, span: int) -> pd.Series:
    return as_series(series).ewm(span=span, adjust=False).mean()


def rolling_max(series: pd.Series, n: int, min_periods: int | None = None) -> pd.Series:
    mp = n if min_periods is None else min_periods
    return as_series(series).rolling(n, min_periods=mp).max()


def rolling_min(series: pd.Series, n: int, min_periods: int | None = None) -> pd.Series:
    mp = n if min_periods is None else min_periods
    return as_series(series).rolling(n, min_periods=mp).min()


def safe_atr(df: pd.DataFrame, n: int) -> pd.Series:
    """Plain ATR with defensive fixes for NaN/Inf/≤0."""
    if len(df) < n:
        return pd.Series(np.nan, index=df.index)

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
    Rolling percentile rank of the last value within the window.
    Returns values in [0,1].
    """
    s = as_series(series)

    def _pct_rank(x: pd.Series) -> float:
        last = x.iloc[-1]
        return float((x <= last).mean())

    return s.rolling(window, min_periods=window).apply(_pct_rank, raw=False)
