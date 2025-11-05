from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.agent.probabilistic.regime import RegimeAnalysisAgent
from app.dal.schemas import SignalFrame


def _build_frames(
    prices: Iterable[float],
    *,
    symbol: str = "AAPL",
    uncertainty: float = 0.01,
) -> list[SignalFrame]:
    frames: list[SignalFrame] = []
    ts_base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for idx, price in enumerate(prices):
        frames.append(
            SignalFrame(
                symbol=symbol,
                vendor="alpaca",
                timestamp=ts_base + timedelta(minutes=idx),
                price=float(price),
                volume=1_000.0,
                filtered_price=float(price),
                velocity=0.0,
                uncertainty=uncertainty,
                butterworth_price=float(price),
                ema_price=float(price),
            )
        )
    return frames


def test_regime_analysis_agent_marks_uncertain_when_uncertainty_spikes() -> None:
    prices = [100.0 + 0.1 * idx for idx in range(15)]
    frames = _build_frames(prices, uncertainty=0.2)

    agent = RegimeAnalysisAgent(window=5)

    snapshots = agent.classify(frames)

    assert all(snapshot.regime == "uncertain" for snapshot in snapshots)


def test_regime_analysis_agent_detects_market_states() -> None:
    agent = RegimeAnalysisAgent(window=10, high_vol_threshold=0.03)

    trend_up_prices = [100.0 + 0.3 * idx for idx in range(40)]
    trend_down_prices = [100.0 - 0.3 * idx for idx in range(40)]
    sideways_prices = [100.0 + (-1.0) ** idx * 1.0 for idx in range(60)]
    high_vol_prices = [100.0 + (-1.0) ** idx * 5.0 for idx in range(60)]

    trend_up = agent.classify(_build_frames(trend_up_prices))
    trend_down = agent.classify(_build_frames(trend_down_prices))
    sideways = agent.classify(_build_frames(sideways_prices))
    high_vol = agent.classify(_build_frames(high_vol_prices))

    assert trend_up[-1].regime == "trend_up"
    assert trend_down[-1].regime == "trend_down"
    assert sideways[-1].regime == "sideways"
    assert high_vol[-1].regime == "high_volatility"
