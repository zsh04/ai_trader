from __future__ import annotations

import pandas as pd
import re
from app.strats.common import ensure_flat_ohlcv, pick_col, ema, rolling_max, rank_percentile


def test_ensure_flat_ohlcv_handles_multiindex():
    cols = pd.MultiIndex.from_product([["OHLC"], ["open", "high", "low", "close"]])
    df = pd.DataFrame([[1, 2, 0, 1]], columns=cols)
    out = ensure_flat_ohlcv(df)
    for c in ["ohlc_open", "ohlc_high", "ohlc_low", "ohlc_close"]:
        assert c in out.columns


def test_pick_col_fallbacks():
    df = pd.DataFrame({"Close_Price": [1.0, 2.0, 3.0]})
    out = pick_col(df, "close", "adj_close", "close_price")
    assert isinstance(out, pd.Series)
    assert out.iloc[-1] == 3.0


def test_rank_percentile_range():
    s = pd.Series([1, 2, 1, 2, 3, 4, 5, 6])
    r = rank_percentile(s, window=4)
    assert 0.0 <= r.dropna().min() <= 1.0
    assert 0.0 <= r.dropna().max() <= 1.0