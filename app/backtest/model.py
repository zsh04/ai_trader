from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BetaWinrate:
    """
    A class for modeling win rate using a Beta distribution.

    Attributes:
        alpha (float): The alpha parameter of the Beta distribution.
        beta (float): The beta parameter of the Beta distribution.
        gate (float): The minimum posterior mean to allow entries.
        fmax (float): The maximum fraction of equity to risk per trade.
    """
    alpha: float = 2.0
    beta: float = 2.0
    gate: float = 0.52
    fmax: float = 0.02

    def p_mean(self) -> float:
        """
        Calculates the posterior mean of the win rate.

        Returns:
            float: The posterior mean of the win rate.
        """
        return self.alpha / (self.alpha + self.beta)

    def allow(self) -> bool:
        """
        Determines whether to allow a trade based on the posterior mean.

        Returns:
            bool: True if the trade is allowed, False otherwise.
        """
        return self.p_mean() >= self.gate

    def kelly_fraction(self) -> float:
        """
        Calculates the Kelly fraction.

        Returns:
            float: The Kelly fraction.
        """
        f_star = max(0.0, 2.0 * self.p_mean() - 1.0)
        return min(self.fmax, f_star)

    def update(self, win: bool) -> None:
        """
        Updates the Beta distribution with the result of a trade.

        Args:
            win (bool): Whether the trade was a win.
        """
        if win:
            self.alpha += 1.0
        else:
            self.beta += 1.0
