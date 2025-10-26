from __future__ import annotations

import pandas as pd

from app.strats.breakout import BreakoutParams, generate_signals


def test_breakout_outputs(toy_ohlcv):
    p = BreakoutParams(lookback=20, ema_fast=20, atr_len=14, atr_mult=2.0)
    out = generate_signals(toy_ohlcv, p)

    # required columns
    for c in ["hh", "ema", "atr", "trail_stop", "long_entry", "long_exit"]:
        assert c in out.columns

    # booleans & no NaNs in signals
    assert out["long_entry"].dtype == bool
    assert out["long_exit"].dtype == bool
    assert not out["long_entry"].isna().any()
    assert not out["long_exit"].isna().any()

    # Should see at least a few signals with our toy data
    assert int(out["long_entry"].sum()) >= 1
    assert int(out["long_exit"].sum()) >= 1

    # ATR is positive
    assert (out["atr"].fillna(0) >= 0).all()