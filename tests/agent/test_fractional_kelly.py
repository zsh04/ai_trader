from __future__ import annotations

from app.agent.risk import FractionalKellyAgent


def test_fractional_kelly_agent_bounds():
    agent = FractionalKellyAgent(fraction=0.5, min_fraction=0.01, max_fraction=0.05)
    assert abs(agent(0.6, payoff=1.0) - 0.05) < 1e-6  # capped at max
    assert abs(agent(0.2, payoff=1.0) - 0.01) < 1e-6  # floored at min


def test_fractional_kelly_agent_scales():
    agent = FractionalKellyAgent(fraction=0.25, min_fraction=0.005, max_fraction=0.05)
    value = agent(0.7, payoff=2.0)
    assert 0.005 <= value <= 0.05
