from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.agent.probabilistic.signal_filter import FilterConfig, SignalFilteringAgent
from app.dal.schemas import Bar, Bars


def _build_bars(prices: list[float], *, symbol: str = "AAPL") -> Bars:
    ts_base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = Bars(symbol=symbol, vendor="alpaca", timezone="UTC")
    for idx, price in enumerate(prices):
        timestamp = ts_base + timedelta(minutes=idx)
        bars.append(
            Bar(
                symbol=symbol,
                vendor="alpaca",
                timestamp=timestamp,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1_000.0,
            )
        )
    return bars


def test_signal_filtering_agent_returns_empty_list_for_empty_bars() -> None:
    agent = SignalFilteringAgent()
    empty_bars = Bars(symbol="AAPL", vendor="alpaca", timezone="UTC")

    frames = agent.run(empty_bars)

    assert frames == []


def test_signal_filtering_agent_smooths_high_frequency_noise() -> None:
    trend = [100.0 + 0.5 * idx for idx in range(60)]
    noise = [(-1.0) ** idx * 2.0 for idx in range(60)]
    prices = [t + n for t, n in zip(trend, noise, strict=True)]
    bars = _build_bars(prices)

    config = FilterConfig(butterworth_cutoff=0.15, butterworth_order=2, ema_span=8)
    agent = SignalFilteringAgent(config)

    frames = agent.run(bars)

    assert len(frames) == len(prices)
    butterworth = np.array([frame.butterworth_price for frame in frames], dtype=float)
    ema = np.array([frame.ema_price for frame in frames], dtype=float)
    filtered = np.array([frame.filtered_price for frame in frames], dtype=float)
    uncertainties = np.array([frame.uncertainty for frame in frames], dtype=float)
    velocities = np.array([frame.velocity for frame in frames], dtype=float)

    trend_arr = np.array(trend, dtype=float)
    prices_arr = np.array(prices, dtype=float)

    price_step_variation = float(np.mean(np.abs(np.diff(prices_arr))))
    butterworth_step_variation = float(np.mean(np.abs(np.diff(butterworth))))
    ema_step_variation = float(np.mean(np.abs(np.diff(ema))))

    assert np.all(np.isfinite(butterworth))
    assert np.all(np.isfinite(ema))
    assert butterworth_step_variation < price_step_variation
    assert ema_step_variation < price_step_variation
    assert np.all(uncertainties >= 0.0)
    assert velocities[-1] > 0.0
    assert filtered[-1] == pytest.approx(trend_arr[-1], abs=2.0)
