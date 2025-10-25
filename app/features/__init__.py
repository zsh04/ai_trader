"""
AI Trader — Feature Engineering Package

This package includes:
- `indicators`: core technical indicators (RSI, SMA, EMA, ATR)
- `mtf_aggregate`: multi-timeframe aggregation and derived features

Usage:
    from app.features import indicators, mtf_aggregate

All modules under this package are designed to be vectorized, testable,
and safe for async integration (no I/O, pure pandas operations).
"""

from . import indicators, mtf_aggregate

__all__ = ["indicators", "mtf_aggregate"]
