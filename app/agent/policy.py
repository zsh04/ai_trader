"""
Trading policy primitives — strategy-agnostic.

These helpers gate entries/exits using probabilistic signals and basic risk rules.
They are deliberately lightweight and have no external deps so they can be used
from backtests, live execution, or Telegram commands.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isnan
from time import time
from typing import Optional, Tuple


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyConfig:
    """Policy parameters with sane defaults.

    enter_prob: probability threshold to allow a new long entry
    exit_prob:  probability threshold to force an exit (hysteresis)
    max_risk_fraction: fraction of equity you are willing to risk per trade (0–1)
    cooldown_sec: min seconds after an exit before a new entry in the same symbol
    min_hold_sec: minimum seconds to hold after entry before evaluating exit rules
    """

    enter_prob: float = 0.55
    exit_prob: float = 0.45
    max_risk_fraction: float = 0.01
    cooldown_sec: int = 0
    min_hold_sec: int = 0


DEFAULT = PolicyConfig()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _valid_prob(x: Optional[float]) -> bool:
    return x is not None and 0.0 <= x <= 1.0 and not isnan(x)


# -----------------------------------------------------------------------------
# Entry / Exit rules
# -----------------------------------------------------------------------------

def should_enter(signal_prob: Optional[float], cfg: PolicyConfig = DEFAULT) -> bool:
    """Gate a long entry by probability.

    Uses a single threshold (cfg.enter_prob). Make sure caller enforces session/market-hours
    and symbol-specific risk separately.
    """
    return _valid_prob(signal_prob) and float(signal_prob) >= cfg.enter_prob


def should_exit(
    current_prob: Optional[float],
    *,
    price_breached_stop: bool = False,
    price_hit_target: bool = False,
    seconds_in_trade: Optional[int] = None,
    cfg: PolicyConfig = DEFAULT,
) -> Tuple[bool, str]:
    """Return (exit?, reason).

    Exit if:
      • stop was breached
      • target was hit
      • probability deteriorates below cfg.exit_prob (after min hold)
    """
    # Hard price-based rules dominate
    if price_breached_stop:
        return True, "stop"
    if price_hit_target:
        return True, "target"

    # Probability-based exit (with minimum hold window)
    if seconds_in_trade is not None and seconds_in_trade < cfg.min_hold_sec:
        return False, "min_hold"

    if _valid_prob(current_prob) and float(current_prob) < cfg.exit_prob:
        return True, "prob"

    return False, "hold"


# -----------------------------------------------------------------------------
# Cooldown / Risk budget
# -----------------------------------------------------------------------------

def cooldown_active(
    last_exit_ts: Optional[float],
    now_ts: Optional[float] = None,
    cfg: PolicyConfig = DEFAULT,
) -> bool:
    """True if a cool-down window is still active since the last exit."""
    if not last_exit_ts or cfg.cooldown_sec <= 0:
        return False
    now = now_ts if now_ts is not None else time()
    return (now - last_exit_ts) < cfg.cooldown_sec


def risk_budget(equity: float, cfg: PolicyConfig = DEFAULT) -> float:
    """Amount of PnL you are allowed to risk for *one* position, in $.

    Caller can divide by per-share risk to derive position size.
    """
    if equity <= 0:
        return 0.0
    f = max(0.0, min(1.0, cfg.max_risk_fraction))
    return equity * f


__all__ = [
    "PolicyConfig",
    "DEFAULT",
    "should_enter",
    "should_exit",
    "cooldown_active",
    "risk_budget",
]