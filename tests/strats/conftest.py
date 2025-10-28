from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def toy_ohlcv() -> pd.DataFrame:
    """
    Create a deterministic series with two regimes:
    - Flat/slow climb (no entries)
    - Strong breakout / momentum (entries)
    - Then a fade (exits)
    """
    rng = np.random.default_rng(seed=42)
    n = 400
    idx = pd.date_range("2021-01-01", periods=n, freq="B")

    # Regime: slow drift up, then stronger drift, then flat/down
    drift = np.r_[np.full(150, 0.0002), np.full(150, 0.0015), np.full(100, -0.0003)]
    noise = rng.normal(0.0, 0.006, n)
    ret = drift + noise
    close = 100.0 * np.cumprod(1 + ret)

    high = close * (1 + np.clip(rng.normal(0.003, 0.003, n), 0, None))
    low = close * (1 - np.clip(rng.normal(0.003, 0.003, n), 0, None))
    open_ = pd.Series(close).shift(1).fillna(close[0]).to_numpy()
    vol = rng.integers(1_000_000, 5_000_000, n)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    ).astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": int}
    )
    return df
