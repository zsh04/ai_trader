from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.agent.probabilistic.regime import RegimeSnapshot
from app.dal.schemas import SignalFrame
from app.probability import (
    join_probabilistic_features,
    regimes_to_frame,
    signals_to_frame,
)


def _ts(idx: int) -> datetime:
    return datetime(2024, 1, 1, 9, 30 + idx, tzinfo=timezone.utc)


def test_signals_and_regimes_join():
    base_index = pd.DatetimeIndex([_ts(i).replace(tzinfo=None) for i in range(3)])
    base_df = pd.DataFrame(
        {"open": [1.0, 2.0, 3.0], "close": [1.2, 2.3, 3.4]},
        index=base_index,
    )

    signals = [
        SignalFrame(
            symbol="AAPL",
            vendor="alpaca",
            timestamp=_ts(i),
            price=100 + i,
            volume=1_000 + i,
            filtered_price=100 + i * 0.5,
            velocity=0.1 * i,
            uncertainty=0.01 * i,
            butterworth_price=99 + i,
            ema_price=100 + i * 0.4,
        )
        for i in range(3)
    ]

    regimes = [
        RegimeSnapshot(
            symbol="AAPL",
            timestamp=_ts(i),
            regime="trend_up" if i < 2 else "high_volatility",
            volatility=0.2 + i * 0.1,
            uncertainty=0.05 + i * 0.01,
            momentum=0.3 + i * 0.05,
        )
        for i in range(3)
    ]

    sig_df = signals_to_frame(signals)
    reg_df = regimes_to_frame(regimes)

    assert "prob_filtered_price" in sig_df.columns
    assert "regime_label" in reg_df.columns

    merged = join_probabilistic_features(base_df, signals=signals, regimes=regimes)

    assert "prob_filtered_price" in merged.columns
    assert "regime_label" in merged.columns
    key_latest = _ts(2).replace(tzinfo=None)
    key_mid = _ts(1).replace(tzinfo=None)
    assert merged.loc[key_latest, "regime_label"] == "high_volatility"
    assert merged.loc[key_mid, "prob_uncertainty"] == signals[1].uncertainty
