"""
Execution package.

This package collects order-routing helpers and broker-specific clients.

Example:
    from app.execution import alpaca
    order = alpaca.place_bracket_order(...)
"""

from importlib import import_module
from types import ModuleType
from typing import List

__all__: List[str] = ["alpaca"]


def __getattr__(name: str) -> ModuleType:
    """
    Lazily import submodules on first access to avoid import-time side effects
    (e.g., SDK auth checks).
    """
    if name == "alpaca":
        return import_module(".alpaca_client", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(list(globals().keys()) + __all__)
