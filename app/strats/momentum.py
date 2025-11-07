from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

# Opt-in to pandas future behavior to avoid silent downcasting warnings in fillna/ffill/bfill.
try:
    pd.set_option("future.no_silent_downcasting", True)
except Exception as exc:
    # If running with an older pandas that doesn't support this option, ignore.
    logger.debug("pandas future option unsupported: {}", exc)

from .common import (
    as_series,
    choose_probabilistic_price,
    ema,
    ensure_flat_ohlcv,
    get_param,
    pick_col,
    probabilistic_regime_gate,
    probabilistic_velocity_gate,
    rank_percentile,
    safe_atr,
)


def generate_signals(df: pd.DataFrame, p: Any) -> pd.DataFrame:
    """
    Long-only momentum with EMA trend filter and percentile rank.
    Returns original OHLCV + columns:
        momentum, ema, rank, long_entry, long_exit, mom_z (diagnostic)
    Parameters can be a dict or MomentumParams dataclass.
    """
    out = ensure_flat_ohlcv(df)

    # Resolve columns
    price_series = choose_probabilistic_price(out)
    _high = pick_col(out, "high", "ohlc_high", "h")  # for future use
    _low = pick_col(out, "low", "ohlc_low", "l")  # for future use

    # Params
    roc_lb = int(get_param(p, "roc_lookback", 60))
    ema_fast = int(get_param(p, "ema_fast", 50))
    rank_win = int(get_param(p, "rank_window", 252))
    min_rank = float(get_param(p, "min_rank", 0.80))
    min_roc = float(get_param(p, "min_roc", 0.00))
    exit_on_ema = bool(get_param(p, "exit_on_ema_break", True))
    exit_on_fade = bool(get_param(p, "exit_on_mom_fade", True))
    z_win = int(get_param(p, "z_window", 20))
    enter_samebar = bool(get_param(p, "enter_on_signal_bar", False))

    # Core features
    momentum = as_series(price_series.pct_change(roc_lb))
    trend = ema(price_series, ema_fast)
    rank = rank_percentile(price_series, rank_win)

    # Diagnostics
    mom_mean = momentum.rolling(z_win, min_periods=z_win).mean()
    mom_std = momentum.rolling(z_win, min_periods=z_win).std(ddof=0)
    mom_z = (momentum - mom_mean) / mom_std.replace(0.0, np.nan)

    # Entry / Exit rules
    trend_ok = price_series > trend
    mom_ok = (momentum >= min_roc) & (rank >= min_rank)

    velocity_ok = probabilistic_velocity_gate(
        out, float(get_param(p, "min_prob_velocity", 0.0))
    )
    regime_ok = probabilistic_regime_gate(
        out, get_param(p, "regime_whitelist", ("trend_up", "calm", "sideways"))
    )

    long_entry_sig = trend_ok & mom_ok & velocity_ok & regime_ok
    if not enter_samebar:
        long_entry_sig = long_entry_sig.shift(1)

    ema_exit = (
        (price_series < trend) if exit_on_ema else pd.Series(False, index=out.index)
    )
    fade_exit = (
        (momentum < min_roc) if exit_on_fade else pd.Series(False, index=out.index)
    )
    long_exit_sig = ema_exit | fade_exit

    atr_len = int(get_param(p, "atr_len", 14))
    atr = safe_atr(out, atr_len)
    out["atr"] = atr

    out["prob_price_source"] = price_series
    out["velocity_ok"] = velocity_ok.reindex(out.index, fill_value=True)
    out["regime_ok"] = regime_ok.reindex(out.index, fill_value=True)

    # Persist
    out["momentum"] = momentum
    out["ema"] = trend
    out["rank"] = rank
    out["mom_z"] = mom_z
    out["long_entry"] = long_entry_sig.fillna(False).astype(bool)
    out["long_exit"] = long_exit_sig.fillna(False).astype(bool)

    return out
