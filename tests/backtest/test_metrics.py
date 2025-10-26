from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest import metrics

# Ensure deterministic synthetic series
np.random.seed(1337)


def _equity_df(values):
    idx = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.DataFrame({"equity": np.array(values, dtype=float)}, index=idx)


def test_equity_stats_flat_equity_has_zero_vol_and_drawdown():
    df = _equity_df([100.0] * 120)

    result = metrics.equity_stats(df)

    assert result.vol == pytest.approx(0.0)
    assert result.max_drawdown == 0.0


def test_equity_stats_monotonic_increase_has_positive_sharpe():
    increments = np.abs(np.random.normal(loc=0.4, scale=0.1, size=252))
    equity_curve = 100.0 + np.cumsum(increments)
    df = _equity_df(equity_curve)

    result = metrics.equity_stats(df)

    assert result.sharpe > 0.0
