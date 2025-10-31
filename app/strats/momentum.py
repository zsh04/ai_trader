from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

try:
    pd.set_option("future.no_silent_downcasting", True)
except Exception:
    pass

from .common import (
    as_series,
    ema,
    ensure_flat_ohlcv,
    get_param,
    pick_col,
    rank_percentile,
)


def generate_signals(df: pd.DataFrame, p: Any) -> pd.DataFrame:
    """
    Generates trading signals for a momentum strategy.

    Args:
        df (pd.DataFrame): A DataFrame with OHLCV data.
        p (Any): A dictionary or dataclass with the strategy parameters.

    Returns:
        pd.DataFrame: A DataFrame with the generated signals.
    """
    out = ensure_flat_ohlcv(df)

    close = pick_col(out, "close", "adj_close", "close_price", "c", "ohlc_close")
    high = pick_col(out, "high", "ohlc_high", "h")
    low = pick_col(out, "low", "ohlc_low", "l")

    roc_lb = int(get_param(p, "roc_lookback", 60))
    ema_fast = int(get_param(p, "ema_fast", 50))
    rank_win = int(get_param(p, "rank_window", 252))
    min_rank = float(get_param(p, "min_rank", 0.80))
    min_roc = float(get_param(p, "min_roc", 0.00))
    exit_on_ema = bool(get_param(p, "exit_on_ema_break", True))
    exit_on_fade = bool(get_param(p, "exit_on_mom_fade", True))
    z_win = int(get_param(p, "z_window", 20))
    enter_samebar = bool(get_param(p, "enter_on_signal_bar", False))

    momentum = as_series(close.pct_change(roc_lb))
    trend = ema(close, ema_fast)
    rank = rank_percentile(close, rank_win)

    mom_mean = momentum.rolling(z_win, min_periods=z_win).mean()
    mom_std = momentum.rolling(z_win, min_periods=z_win).std(ddof=0)
    mom_z = (momentum - mom_mean) / mom_std.replace(0.0, np.nan)

    trend_ok = close > trend
    mom_ok = (momentum >= min_roc) & (rank >= min_rank)

    long_entry_sig = trend_ok & mom_ok
    if not enter_samebar:
        long_entry_sig = long_entry_sig.shift(1)

    ema_exit = (close < trend) if exit_on_ema else pd.Series(False, index=out.index)
    fade_exit = (
        (momentum < min_roc) if exit_on_fade else pd.Series(False, index=out.index)
    )
    long_exit_sig = ema_exit | fade_exit

    out["momentum"] = momentum
    out["ema"] = trend
    out["rank"] = rank
    out["mom_z"] = mom_z
    out["long_entry"] = long_entry_sig.fillna(False).astype(bool)
    out["long_exit"] = long_exit_sig.fillna(False).astype(bool)

    return out
