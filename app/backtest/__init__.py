

"""Backtesting engine and strategy evaluation tools for AI Trader.
Provides reusable components for running simulations, computing metrics, and producing diagnostic outputs."""

import logging

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")