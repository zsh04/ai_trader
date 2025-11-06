from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import numpy as np

from app.dal.schemas import SignalFrame


@dataclass(slots=True)
class RegimeSnapshot:
    symbol: str
    timestamp: Optional[datetime]
    regime: str
    volatility: float
    uncertainty: float
    momentum: float


class RegimeAnalysisAgent:
    """Classify probabilistic regimes based on filtered signals and uncertainty."""

    def __init__(
        self,
        *,
        window: int = 20,
        high_vol_threshold: float = 0.02,
        low_vol_threshold: float = 0.005,
        uncertainty_threshold: float = 0.05,
        momentum_threshold: float = 0.001,
    ) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")
        self.window = window
        self.high_vol_threshold = high_vol_threshold
        self.low_vol_threshold = low_vol_threshold
        self.uncertainty_threshold = uncertainty_threshold
        self.momentum_threshold = momentum_threshold

    def classify(self, frames: Iterable[SignalFrame]) -> List[RegimeSnapshot]:
        frames_list = list(frames)
        if not frames_list:
            return []

        prices = np.array(
            [
                (
                    frame.filtered_price
                    if frame.filtered_price is not None
                    else frame.price
                )
                for frame in frames_list
            ]
        )
        returns = np.diff(np.log(prices + 1e-12), prepend=np.log(prices[0] + 1e-12))
        momentum = np.convolve(returns, np.ones(self.window) / self.window, mode="same")

        vol = self._rolling_std(returns, self.window)
        snapshots: List[RegimeSnapshot] = []

        for idx, frame in enumerate(frames_list):
            current_vol = vol[idx]
            current_uncertainty = frame.uncertainty
            current_momentum = momentum[idx]

            if current_uncertainty > self.uncertainty_threshold:
                regime = "uncertain"
            elif current_vol >= self.high_vol_threshold:
                regime = "high_volatility"
            elif current_vol <= self.low_vol_threshold:
                if current_momentum >= self.momentum_threshold:
                    regime = "trend_up"
                elif current_momentum <= -self.momentum_threshold:
                    regime = "trend_down"
                else:
                    regime = "calm"
            else:
                regime = "sideways"

            snapshots.append(
                RegimeSnapshot(
                    symbol=frame.symbol,
                    timestamp=frame.timestamp,
                    regime=regime,
                    volatility=float(current_vol),
                    uncertainty=float(current_uncertainty),
                    momentum=float(current_momentum),
                )
            )

        return snapshots

    def _rolling_std(self, data: np.ndarray, window: int) -> np.ndarray:
        if len(data) < window:
            std = float(np.std(data)) if data.size else 0.0
            return np.full_like(data, std)
        cumsum = np.cumsum(np.insert(data, 0, 0.0))
        cumsum_sq = np.cumsum(np.insert(np.square(data), 0, 0.0))
        means = (cumsum[window:] - cumsum[:-window]) / window
        sq_means = (cumsum_sq[window:] - cumsum_sq[:-window]) / window
        variances = np.maximum(sq_means - np.square(means), 0.0)
        rolling_std = np.sqrt(variances)
        pad_value = rolling_std[0] if rolling_std.size else 0.0
        pad = np.full(window - 1, pad_value)
        return np.concatenate([pad, rolling_std])
