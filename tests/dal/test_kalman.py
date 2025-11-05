from __future__ import annotations

from app.dal.kalman import KalmanConfig, KalmanFilter1D


def test_kalman_filter_velocity_positive():
    filt = KalmanFilter1D(KalmanConfig(process_variance=1e-4, measurement_variance=1e-3))
    prices = [10 + i * 0.5 for i in range(10)]
    last_velocity = None
    for price in prices:
        _, velocity, _ = filt.step(price)
        last_velocity = velocity
    assert last_velocity is not None
    assert last_velocity > 0
