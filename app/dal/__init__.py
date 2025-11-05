"""Probabilistic market data abstraction layer."""

from .kalman import KalmanConfig, KalmanFilter1D
from .results import ProbabilisticBatch, ProbabilisticStreamFrame
from .schemas import Bar, Bars, SignalFrame

__all__ = [
    "MarketDataDAL",
    "KalmanConfig",
    "KalmanFilter1D",
    "ProbabilisticBatch",
    "ProbabilisticStreamFrame",
    "Bar",
    "Bars",
    "SignalFrame",
]


def __getattr__(name: str):
    if name == "MarketDataDAL":
        from .manager import MarketDataDAL as _MarketDataDAL

        return _MarketDataDAL
    raise AttributeError(f"module {__name__} has no attribute {name!r}")
