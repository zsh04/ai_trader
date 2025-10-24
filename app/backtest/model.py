from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BetaWinrate:
    alpha: float = 2.0
    beta: float = 2.0
    gate: float = 0.52  # minimum posterior mean to allow entries
    fmax: float = 0.02  # cap fraction of equity per trade (Kelly cap)

    def p_mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def allow(self) -> bool:
        return self.p_mean() >= self.gate

    def kelly_fraction(self) -> float:
        # 1:1 R payoff approximation
        f_star = max(0.0, 2.0 * self.p_mean() - 1.0)
        return min(self.fmax, f_star)

    def update(self, win: bool) -> None:
        if win:
            self.alpha += 1.0
        else:
            self.beta += 1.0
