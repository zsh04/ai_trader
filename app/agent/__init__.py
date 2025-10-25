
"""
High-level trade agent primitives.

This package contains **pure-Python, data-agnostic** logic used by scanners and
execution components:

- `sizing`: position sizing helpers (risk-based, fixed-fraction, etc.)
- `risk`: guardrails and limit checks (max loss, max exposure, etc.)

Design notes
------------
* Keep modules side‑effect free (no I/O, no environment reads).
* Prefer **explicit imports** over `from … import *` to keep lints happy.
* Keep functions small and unit-testable.

Typical usage
-------------
    from app.agent.sizing import compute_position_size, SizingParams
    from app.agent.risk import RiskLimits, apply_risk_limits

Public API
----------
To avoid brittle wildcard imports, this package does not auto re-export symbols
from submodules. Import directly from the desired module (see examples above).
"""

# The package intentionally exposes no implicit re-exports.
# Downstream code should import from concrete submodules, e.g.:
#   from app.agent.sizing import compute_position_size
#   from app.agent.risk import apply_risk_limits
__all__: list[str] = []