"""
Execution package.

This package collects order-routing helpers and broker-specific clients.

Convenience re-exports:
- `alpaca`: lazy module proxy to `app.execution.alpaca_client`
- `router`: lazy module proxy to `app.execution.router`

Example:
    from app.execution import alpaca, router
    order = alpaca.place_bracket_order(...)
    tp, sl = router.compute_bracket_levels(...)
"""

from importlib import import_module
from types import ModuleType
from typing import List

__all__: List[str] = ["alpaca", "router"]


def __getattr__(name: str) -> ModuleType:
    """
    Lazily import submodules on first access to avoid import-time side effects
    (e.g., SDK auth checks).
    """
    if name == "alpaca":
        return import_module(".alpaca_client", __name__)
    if name == "router":
        return import_module(".router", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(list(globals().keys()) + __all__)
