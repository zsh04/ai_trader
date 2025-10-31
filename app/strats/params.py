from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MomentumParams:
    """
    A data class for momentum strategy parameters.

    Attributes:
        roc_lookback (int): The lookback period for the rate of change.
        ema_fast (int): The fast EMA period for the trend filter.
        rank_window (int): The window for percentile ranking.
        min_rank (float): The minimum percentile rank for entry.
        min_roc (float): The minimum rate of change for entry.
        exit_on_ema_break (bool): Whether to exit on EMA break.
        exit_on_mom_fade (bool): Whether to exit on momentum fade.
        atr_len (int): The ATR period for stop loss and sizing.
        atr_mult (float): The ATR multiplier for the initial stop distance.
        entry_price (str): The entry price type.
        enter_on_signal_bar (bool): Whether to enter on the same bar as the signal.
        z_window (int): The window for z-scoring momentum.
    """
    roc_lookback: int = 60
    ema_fast: int = 50
    rank_window: int = 252
    min_rank: float = 0.80
    min_roc: float = 0.00
    exit_on_ema_break: bool = True
    exit_on_mom_fade: bool = True
    atr_len: int = 14
    atr_mult: float = 2.0
    entry_price: str = "close"
    enter_on_signal_bar: bool = False
    z_window: int = 20
