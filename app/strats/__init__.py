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
from .params import MomentumParams
from .momentum import generate_signals as momentum_signals

__all__ = [
    "BreakoutParams",
    "breakout_signals",
    "MomentumParams",
    "momentum_signals",
]