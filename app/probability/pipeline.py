from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from app.agent.probabilistic.regime import RegimeSnapshot
from app.dal.manager import MarketDataDAL
from app.dal.results import ProbabilisticBatch
from app.dal.schemas import SignalFrame


@dataclass(slots=True)
class ProbabilisticConfig:
    """Configuration for fetching probabilistic features."""

    vendor: str = "alpaca"
    interval: str = "1Min"
    enable_metadata_persist: bool = False


def fetch_probabilistic_batch(
    symbol: str,
    *,
    start: datetime,
    end: Optional[datetime] = None,
    config: Optional[ProbabilisticConfig] = None,
    dal: Optional[MarketDataDAL] = None,
) -> ProbabilisticBatch:
    """
    Retrieve probabilistic market data for a symbol using MarketDataDAL.
    """
    cfg = config or ProbabilisticConfig()
    dal_instance = dal or MarketDataDAL(
        enable_postgres_metadata=cfg.enable_metadata_persist
    )
    return dal_instance.fetch_bars(
        symbol=symbol,
        start=start,
        end=end,
        interval=cfg.interval,
        vendor=cfg.vendor,
    )


def _normalize_index(index: Iterable[datetime]) -> pd.DatetimeIndex:
    idx = pd.to_datetime(list(index))
    tz = getattr(idx, "tz", None)
    if tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx


def signals_to_frame(signals: list[SignalFrame]) -> pd.DataFrame:
    """Convert SignalFrame list to DataFrame keyed by timestamp."""
    if not signals:
        return pd.DataFrame()
    records = [
        {
            "timestamp": frame.timestamp,
            "prob_price": frame.price,
            "prob_volume": frame.volume,
            "prob_filtered_price": frame.filtered_price,
            "prob_velocity": frame.velocity,
            "prob_uncertainty": frame.uncertainty,
            "prob_butterworth_price": frame.butterworth_price,
            "prob_ema_price": frame.ema_price,
        }
        for frame in signals
    ]
    df = pd.DataFrame(records)
    idx = _normalize_index(df.pop("timestamp"))
    df.index = idx
    df = df.groupby(level=0).last()
    return df.sort_index()


def regimes_to_frame(regimes: list[RegimeSnapshot]) -> pd.DataFrame:
    """Convert regime snapshots to a DataFrame keyed by timestamp."""
    rows = []
    for snapshot in regimes or []:
        if snapshot.timestamp is None:
            continue
        rows.append(
            {
                "timestamp": snapshot.timestamp,
                "regime_label": snapshot.regime,
                "regime_volatility": snapshot.volatility,
                "regime_uncertainty": snapshot.uncertainty,
                "regime_momentum": snapshot.momentum,
            }
        )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    idx = _normalize_index(df.pop("timestamp"))
    df.index = idx
    df = df.groupby(level=0).last()
    return df.sort_index()





def infer_probabilistic_success(sig: pd.DataFrame) -> float:
    """
    Infer probability of trade success based on probabilistic features.
    
    Uses:
    - prob_velocity (tanh scaled)
    - prob_uncertainty (linear penalty)
    - regime_label (categorical adjustments)
    """
    probability = 0.55
    vel = sig.get("prob_velocity")
    if vel is not None:
        # Handle both Series and scalar (though usually Series in a frame context)
        # If Series, take the last non-NaN
        if hasattr(vel, "dropna"):
            valid = vel.dropna()
            if not valid.empty:
                probability = 0.5 + 0.5 * np.tanh(float(valid.iloc[-1]))
        elif pd.notnull(vel):
             probability = 0.5 + 0.5 * np.tanh(float(vel))

    uncertainty = sig.get("prob_uncertainty")
    if uncertainty is not None:
        if hasattr(uncertainty, "dropna"):
            valid = uncertainty.dropna()
            if not valid.empty:
                probability -= float(valid.iloc[-1])
        elif pd.notnull(uncertainty):
            probability -= float(uncertainty)

    regime = sig.get("regime_label")
    if regime is not None:
        latest = None
        if hasattr(regime, "dropna"):
            valid = regime.dropna()
            if not valid.empty:
                latest = str(valid.iloc[-1]).lower()
        elif pd.notnull(regime):
            latest = str(regime).lower()
        
        if latest:
            probability += {
                "trend_up": 0.05,
                "calm": 0.02,
                "sideways": 0.0,
                "trend_down": -0.07,
                "high_volatility": -0.08,
                "uncertain": -0.1,
            }.get(latest, 0.0)

    return max(0.05, min(0.95, probability))


def join_probabilistic_features(
    df: pd.DataFrame,
    *,
    signals: Optional[list[SignalFrame]] = None,
    regimes: Optional[list[RegimeSnapshot]] = None,
) -> pd.DataFrame:
    """
    Join probabilistic signal/regime features onto an existing DataFrame.
    """
    out = df.copy()
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_convert("UTC").tz_localize(None)
    sig_df = signals_to_frame(signals or [])
    reg_df = regimes_to_frame(regimes or [])
    if not sig_df.empty:
        out = out.join(sig_df, how="left")
    if not reg_df.empty:
        out = out.join(reg_df, how="left")
    return out
