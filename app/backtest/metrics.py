from __future__ import annotations

import numpy as np
import pandas as pd


def metrics(equity: pd.DataFrame) -> dict:
    eq = equity["equity"].astype(float)
    rets = eq.pct_change().fillna(0.0)
    total_ret = eq.iloc[-1] / eq.iloc[0] - 1.0
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (1 + total_ret) ** (1 / max(years, 1e-6)) - 1.0
    roll = (eq / eq.cummax()) - 1.0
    mdd = roll.min()
    sharpe = (rets.mean() / (rets.std() + 1e-12)) * np.sqrt(252.0)
    return {
        "TotalReturn": total_ret,
        "CAGR": cagr,
        "MaxDD": float(mdd),
        "Sharpe": float(sharpe),
    }
