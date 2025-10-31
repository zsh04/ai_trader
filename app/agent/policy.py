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
    """
    Policy parameters with sane defaults.

    Attributes:
        enter_prob (float): Probability threshold to allow a new long entry.
        exit_prob (float): Probability threshold to force an exit.
        max_risk_fraction (float): Fraction of equity to risk per trade.
        cooldown_sec (int): Minimum seconds after an exit before a new entry.
        min_hold_sec (int): Minimum seconds to hold after entry.
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
    """
    Checks if a value is a valid probability.

    Args:
        x (Optional[float]): The value to check.

    Returns:
        bool: True if the value is a valid probability, False otherwise.
    """
    return x is not None and 0.0 <= x <= 1.0 and not isnan(x)


# -----------------------------------------------------------------------------
# Entry / Exit rules
# -----------------------------------------------------------------------------


def should_enter(signal_prob: Optional[float], cfg: PolicyConfig = DEFAULT) -> bool:
    """
    Determines whether to enter a long position.

    Args:
        signal_prob (Optional[float]): The probability of the entry signal.
        cfg (PolicyConfig): The policy configuration.

    Returns:
        bool: True if the entry is allowed, False otherwise.
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
    """
    Determines whether to exit a position.

    Args:
        current_prob (Optional[float]): The current probability of the signal.
        price_breached_stop (bool): Whether the price has breached the stop loss.
        price_hit_target (bool): Whether the price has hit the target.
        seconds_in_trade (Optional[int]): The number of seconds in the trade.
        cfg (PolicyConfig): The policy configuration.

    Returns:
        Tuple[bool, str]: A tuple of (exit?, reason).
    """
    if price_breached_stop:
        return True, "stop"
    if price_hit_target:
        return True, "target"

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
    """
    Checks if a cooldown period is active.

    Args:
        last_exit_ts (Optional[float]): The timestamp of the last exit.
        now_ts (Optional[float]): The current timestamp.
        cfg (PolicyConfig): The policy configuration.

    Returns:
        bool: True if a cooldown is active, False otherwise.
    """
    if not last_exit_ts or cfg.cooldown_sec <= 0:
        return False
    now = now_ts if now_ts is not None else time()
    return (now - last_exit_ts) < cfg.cooldown_sec


def risk_budget(equity: float, cfg: PolicyConfig = DEFAULT) -> float:
    """
    Calculates the risk budget for a single position.

    Args:
        equity (float): The current equity.
        cfg (PolicyConfig): The policy configuration.

    Returns:
        float: The risk budget in dollars.
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
