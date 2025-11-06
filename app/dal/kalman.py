from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class KalmanConfig:
    """Configuration for a simple constant-velocity Kalman filter."""

    process_variance: float = 1e-3
    measurement_variance: float = 1e-2
    dt: float = 1.0  # time delta between measurements, default 1 unit


class KalmanFilter1D:
    """Constant-velocity Kalman filter tracking price and velocity."""

    def __init__(self, config: KalmanConfig | None = None) -> None:
        cfg = config or KalmanConfig()
        self.q = cfg.process_variance
        self.r = cfg.measurement_variance
        self.dt = cfg.dt
        self.reset()

    def reset(self) -> None:
        self.x = 0.0  # position / price
        self.v = 0.0  # velocity
        self.p11 = 1.0
        self.p12 = 0.0
        self.p21 = 0.0
        self.p22 = 1.0
        self._initialized = False

    def step(self, price: float) -> Tuple[float, float, float]:
        """Consume a new price observation and return (filtered_price, velocity, uncertainty)."""
        if not self._initialized:
            self.x = price
            self.v = 0.0
            self._initialized = True
            return price, 0.0, self.p11

        # Prediction step
        x_pred = self.x + self.v * self.dt
        v_pred = self.v
        p11_pred = (
            self.p11 + (self.p12 + self.p21 + self.p22 * self.dt) * self.dt + self.q
        )
        p12_pred = self.p12 + self.p22 * self.dt
        p21_pred = self.p21 + self.p22 * self.dt
        p22_pred = self.p22 + self.q

        # Innovation
        y = price - x_pred
        s = p11_pred + self.r
        k1 = p11_pred / s
        k2 = p21_pred / s

        # Update
        self.x = x_pred + k1 * y
        self.v = v_pred + k2 * y
        self.p11 = (1 - k1) * p11_pred
        self.p12 = (1 - k1) * p12_pred
        self.p21 = p21_pred - k2 * p11_pred
        self.p22 = p22_pred - k2 * p12_pred

        uncertainty = max(self.p11, 0.0)
        return self.x, self.v, uncertainty


__all__ = ["KalmanFilter1D", "KalmanConfig"]
