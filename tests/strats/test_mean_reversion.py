from __future__ import annotations

import numpy as np
import pandas as pd

from app.strats.mean_reversion import generate_signals
from app.strats.params import MeanReversionParams


def test_mean_reversion_uses_probabilistic_price_and_zscore():
    idx = pd.date_range("2025-01-01", periods=30, freq="D")
    base = 100 + np.sin(np.linspace(0, 4 * np.pi, len(idx)))
    prob_price = base + np.linspace(0, 2, len(idx))
    df = pd.DataFrame(
        {
            "open": base + 0.1,
            "high": base + 1.0,
            "low": base - 1.0,
            "close": base,
            "prob_filtered_price": prob_price,
            "prob_velocity": np.linspace(0.0, 0.1, len(idx)),
            "regime_label": ["calm"] * len(idx),
        },
        index=idx,
    )

    params = MeanReversionParams(lookback=10, z_entry=-0.3, z_exit=0.0)

    sig = generate_signals(df, params)

    assert "z_score" in sig
    assert "atr" in sig

    entry_dates = sig.index[sig["long_entry"]]
    assert len(entry_dates) > 0

    exit_dates = sig.index[sig["long_exit"]]
    assert len(exit_dates) > 0
