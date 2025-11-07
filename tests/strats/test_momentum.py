from __future__ import annotations

import numpy as np
import pandas as pd

from app.strats.momentum import generate_signals
from app.strats.params import MomentumParams


def _build_prob_df() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=10, freq="D")
    base = np.linspace(100, 109, len(idx))
    prob_price = base + np.linspace(0, 5, len(idx))
    velocity = np.linspace(0.02, 0.2, len(idx))
    velocity[4] = -0.1  # force gating
    regimes = ["trend_up"] * len(idx)
    regimes[6] = "high_volatility"

    df = pd.DataFrame(
        {
            "open": base + 0.5,
            "high": base + 1.0,
            "low": base - 1.0,
            "close": base,
            "prob_filtered_price": prob_price,
            "prob_velocity": velocity,
            "regime_label": regimes,
        },
        index=idx,
    )
    return df


def test_momentum_respects_probabilistic_price_velocity_and_regime():
    df = _build_prob_df()
    params = MomentumParams(
        roc_lookback=2,
        ema_fast=2,
        rank_window=3,
        min_rank=0.0,
        min_roc=-1.0,
        atr_len=2,
        atr_mult=1.5,
        enter_on_signal_bar=True,
        min_prob_velocity=0.01,
        regime_whitelist=("trend_up",),
    )

    sig = generate_signals(df, params)

    assert "atr" in sig
    assert sig["atr"].notna().all()

    expected = pd.Series(df["prob_filtered_price"].pct_change(2), index=sig.index)
    pd.testing.assert_series_equal(
        sig["momentum"].round(10), expected.round(10), check_names=False
    )

    # Velocity < threshold and non-whitelisted regime should block entries
    assert not sig.loc[sig.index[4], "long_entry"]  # velocity gate
    assert not sig.loc[sig.index[6], "long_entry"]  # regime gate

    # Once conditions satisfied, entry should appear
    entry_candidates = sig.loc[(sig.index > df.index[3]) & (sig["velocity_ok"])]
    assert entry_candidates["long_entry"].any()
