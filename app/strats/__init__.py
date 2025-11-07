from __future__ import annotations

# Public API for strategies

# Re-export breakout’s public bits without modifying breakout.py right now.
try:
    from .breakout import BreakoutParams as BreakoutParams  # type: ignore
    from .breakout import generate_signals as breakout_signals  # type: ignore
except Exception:  # breakout exists in your tree; this keeps imports resilient
    BreakoutParams = object  # fallback type

    def breakout_signals(*args, **kwargs):  # type: ignore
        raise RuntimeError("breakout strategy not available")


# Momentum strategy
from .mean_reversion import generate_signals as mean_reversion_signals
from .momentum import generate_signals as momentum_signals
from .params import MeanReversionParams, MomentumParams

__all__ = [
    "BreakoutParams",
    "breakout_signals",
    "MomentumParams",
    "momentum_signals",
    "MeanReversionParams",
    "mean_reversion_signals",
]
