from __future__ import annotations

import pandas as pd

from app.backtest.run_breakout import infer_probabilistic_success


def test_infer_probabilistic_success_velocity_and_regime():
    df = pd.DataFrame(
        {
            "prob_velocity": [0.1, 0.2],
            "regime_label": ["trend_up", "calm"],
            "prob_uncertainty": [0.01, 0.01],
        }
    )
    prob = infer_probabilistic_success(df)
    assert prob > 0.55


def test_infer_probabilistic_success_penalizes_uncertainty():
    df = pd.DataFrame(
        {
            "prob_velocity": [0.02, 0.02],
            "regime_label": ["uncertain", "uncertain"],
            "prob_uncertainty": [0.2, 0.25],
        }
    )
    prob = infer_probabilistic_success(df)
    assert prob < 0.5
