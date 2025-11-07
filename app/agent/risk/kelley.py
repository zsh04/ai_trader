from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FractionalKellyAgent:
    """Simple fractional Kelly sizing helper."""

    fraction: float = 0.5
    min_fraction: float = 0.0025
    max_fraction: float = 0.05

    def __call__(self, probability: float, payoff: float = 1.0) -> float:
        prob = max(0.01, min(0.99, probability))
        payoff = max(0.01, payoff)
        edge = prob * (payoff + 1.0) - 1.0
        kelly = edge / payoff
        scaled = kelly * self.fraction
        return max(self.min_fraction, min(self.max_fraction, scaled))
