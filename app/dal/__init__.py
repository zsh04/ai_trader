"""Probabilistic market data abstraction layer."""

from .kalman import KalmanConfig, KalmanFilter1D
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
    if name in {"ProbabilisticBatch", "ProbabilisticStreamFrame"}:
        from .results import ProbabilisticBatch as _ProbabilisticBatch  # local import
        from .results import ProbabilisticStreamFrame as _ProbabilisticStreamFrame

        return (
            _ProbabilisticBatch
            if name == "ProbabilisticBatch"
            else _ProbabilisticStreamFrame
        )
    raise AttributeError(f"module {__name__} has no attribute {name!r}")
