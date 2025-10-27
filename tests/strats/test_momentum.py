from __future__ import annotations

import pandas as pd
import re
from app.strats.params import MomentumParams
from app.strats.momentum import generate_signals


def test_momentum_outputs(toy_ohlcv):
    p = MomentumParams(
        roc_lookback=60,
        ema_fast=50,
        rank_window=120,   # smaller for quicker non-NaN
        min_rank=0.6,
        min_roc=-0.01,
    )
    out = generate_signals(toy_ohlcv, p)

    for c in ["momentum", "ema", "rank", "long_entry", "long_exit"]:
        assert c in out.columns

    assert out["long_entry"].dtype == bool
    assert out["long_exit"].dtype == bool

    # With our toy series we should get some signals
    assert int(out["long_entry"].sum()) >= 1
    assert int(out["long_exit"].sum()) >= 1

    # Diagnostics present (optional)
    assert "mom_z" in out.columns