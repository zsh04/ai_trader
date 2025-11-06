from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from app.dal.kalman import KalmanConfig, KalmanFilter1D
from app.dal.schemas import Bars, SignalFrame


@dataclass(slots=True)
class FilterConfig:
    """Configuration options for probabilistic signal filtering."""

    kalman: Optional[KalmanConfig] = field(default_factory=KalmanConfig)
    butterworth_cutoff: float = 0.1  # fraction of Nyquist (0, 0.5)
    butterworth_order: int = 2
    ema_span: int = 10


class SignalFilteringAgent:
    """Combine Kalman, Butterworth, and EMA filters to emit probabilistic signals."""

    def __init__(self, config: Optional[FilterConfig] = None) -> None:
        self.config = config or FilterConfig()
        self._kalman: KalmanFilter1D | None = None
        self._ema_prev: Optional[float] = None
        self._ema_alpha: Optional[float] = None
        self._butter_coeffs: Optional[tuple[float, float, float, float, float]] = None
        self._butter_x1: Optional[float] = None
        self._butter_x2: Optional[float] = None
        self._butter_y1: Optional[float] = None
        self._butter_y2: Optional[float] = None
        self.reset()

    def run(self, bars: Bars) -> List[SignalFrame]:
        prices = [bar.close for bar in bars.data]
        volumes = [bar.volume for bar in bars.data]
        timestamps = [bar.timestamp for bar in bars.data]
        if not prices:
            return []

        self.reset()
        frames: List[SignalFrame] = []
        for idx, price in enumerate(prices):
            frames.append(
                self.step(
                    symbol=bars.symbol,
                    vendor=bars.vendor,
                    timestamp=timestamps[idx],
                    price=price,
                    volume=volumes[idx],
                )
            )
        return frames

    def reset(self) -> None:
        """Reset filter state so the agent can process a fresh sequence."""
        self._kalman = KalmanFilter1D(self.config.kalman)
        if self.config.ema_span > 1:
            self._ema_alpha = 2.0 / (self.config.ema_span + 1.0)
        else:
            self._ema_alpha = None
        self._ema_prev = None
        self._butter_coeffs = self._compute_butterworth_coeffs(
            self.config.butterworth_cutoff, self.config.butterworth_order
        )
        self._butter_x1 = None
        self._butter_x2 = None
        self._butter_y1 = None
        self._butter_y2 = None

    def step(
        self,
        *,
        symbol: str,
        vendor: str,
        timestamp: datetime,
        price: float,
        volume: float,
    ) -> SignalFrame:
        """Process a single observation and return the resulting SignalFrame."""
        if self._kalman is None:
            self.reset()

        filtered, velocity, uncertainty = self._kalman.step(float(price))
        butterworth_price = self._butterworth_step(float(price))
        ema_price = self._ema_step(float(price))

        return SignalFrame(
            symbol=symbol,
            vendor=vendor,
            timestamp=timestamp,
            price=float(price),
            volume=float(volume),
            filtered_price=filtered,
            velocity=velocity,
            uncertainty=uncertainty,
            butterworth_price=butterworth_price,
            ema_price=ema_price,
        )

    def _compute_butterworth_coeffs(
        self, cutoff: float, order: int
    ) -> tuple[float, float, float, float, float]:
        cutoff = min(max(cutoff, 1e-5), 0.49)
        ita = 1.0 / math.tan(math.pi * cutoff)
        b0 = 1.0 / (1.0 + math.sqrt(2) * ita + ita * ita)
        b1 = 2.0 * b0
        b2 = b0
        a1 = 2.0 * (ita * ita - 1.0) / (1.0 + math.sqrt(2) * ita + ita * ita)
        a2 = (1.0 - math.sqrt(2) * ita + ita * ita) / (
            1.0 + math.sqrt(2) * ita + ita * ita
        )
        return b0, b1, b2, a1, a2

    def _butterworth_step(self, price: float) -> float:
        if self._butter_coeffs is None:
            return price
        b0, b1, b2, a1, a2 = self._butter_coeffs
        if self._butter_y1 is None:
            y = b0 * price
        elif self._butter_y2 is None or self._butter_x2 is None:
            prev_x1 = self._butter_x1 if self._butter_x1 is not None else price
            prev_y1 = self._butter_y1
            y = b0 * price + b1 * prev_x1 - a1 * prev_y1
        else:
            prev_x1 = self._butter_x1 if self._butter_x1 is not None else price
            prev_x2 = self._butter_x2
            prev_y1 = self._butter_y1
            prev_y2 = self._butter_y2
            y = b0 * price + b1 * prev_x1 + b2 * prev_x2 - a1 * prev_y1 - a2 * prev_y2

        self._butter_x2 = self._butter_x1
        self._butter_x1 = price
        self._butter_y2 = self._butter_y1
        self._butter_y1 = y
        return y

    def _ema_step(self, price: float) -> float:
        if self._ema_alpha is None:
            return price
        if self._ema_prev is None:
            self._ema_prev = price
        else:
            self._ema_prev = (
                self._ema_alpha * price + (1.0 - self._ema_alpha) * self._ema_prev
            )
        return self._ema_prev
