from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class MomentumParams:
    # Core signal
    roc_lookback: int = 60  # N-day rate of change
    ema_fast: int = 50  # trend filter
    rank_window: int = 252  # ~1y daily lookback for percentile rank
    min_rank: float = 0.80  # require >= 80th percentile
    min_roc: float = 0.00  # require non-negative ROC by default

    # Exits
    exit_on_ema_break: bool = True
    exit_on_mom_fade: bool = True  # exit if momentum < min_roc again

    # Sizing / safety (optional; not used for entry by default)
    atr_len: int = 14
    atr_mult: float = 2.0

    # Execution semantics
    entry_price: str = "close"  # "close" or "next_open"
    enter_on_signal_bar: bool = False  # False → use next bar semantics

    # Diagnostics
    z_window: int = 20  # for optional z-scoring of momentum

    # Probabilistic gating
    min_prob_velocity: float = 0.0  # require velocity >= threshold when available
    regime_whitelist: Tuple[str, ...] = ("trend_up", "calm", "sideways")


@dataclass(frozen=True)
class MeanReversionParams:
    lookback: int = 20
    z_entry: float = -2.0
    z_exit: float = -0.5
    atr_len: int = 14
    atr_mult: float = 1.5
    entry_price: str = "close"
    enter_on_signal_bar: bool = False
    min_prob_velocity: float = -1.0
    regime_whitelist: Tuple[str, ...] = ("calm", "sideways", "trend_up")
