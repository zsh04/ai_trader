from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from .common import (
    choose_probabilistic_price,
    ensure_flat_ohlcv,
    probabilistic_regime_gate,
    probabilistic_velocity_gate,
    safe_atr,
)

try:
    pd.set_option("future.no_silent_downcasting", True)
except Exception as exc:  # pragma: no cover - optional
    logger.debug("pandas future option unsupported: {}", exc)


def generate_signals(df: pd.DataFrame, params: object) -> pd.DataFrame:
    out = ensure_flat_ohlcv(df)

    price = choose_probabilistic_price(out)

    lookback = int(getattr(params, "lookback", 20))
    z_entry = float(getattr(params, "z_entry", -2.0))
    z_exit = float(getattr(params, "z_exit", -0.5))
    min_velocity = float(getattr(params, "min_prob_velocity", -1.0))
    regime_whitelist = getattr(params, "regime_whitelist", ("calm", "sideways"))

    mean = price.rolling(lookback, min_periods=lookback).mean()
    std = price.rolling(lookback, min_periods=lookback).std(ddof=0)
    std = std.replace(0.0, np.nan)
    z_score = (price - mean) / std

    velocity_ok = probabilistic_velocity_gate(out, min_velocity)
    regime_ok = probabilistic_regime_gate(out, regime_whitelist)

    long_entry = (z_score <= z_entry) & velocity_ok & regime_ok
    long_exit = (z_score >= z_exit) | z_score.isna()

    enter_samebar = bool(getattr(params, "enter_on_signal_bar", False))
    if not enter_samebar:
        long_entry = long_entry.shift(1)
        long_exit = long_exit.shift(1)

    atr_len = int(getattr(params, "atr_len", 14))
    atr = safe_atr(out, atr_len)

    out["mean"] = mean
    out["std"] = std
    out["z_score"] = z_score
    out["long_entry"] = long_entry.fillna(False).astype(bool)
    out["long_exit"] = long_exit.fillna(False).astype(bool)
    out["atr"] = atr
    out["prob_price_source"] = price
    out["velocity_ok"] = velocity_ok.reindex(out.index, fill_value=True)
    out["regime_ok"] = regime_ok.reindex(out.index, fill_value=True)

    return out
