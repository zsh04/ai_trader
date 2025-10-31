import logging
import math
from typing import Tuple

log = logging.getLogger(__name__)


def bracket_for_entry(
    entry_px: float, atr: float, tp_mult: float = 1.5, sl_mult: float = 1.0
) -> Tuple[float, float]:
    """
    Computes take-profit and stop-loss price levels for an entry.

    Args:
        entry_px (float): The entry price of the position.
        atr (float): The Average True Range (ATR) as a volatility measure.
        tp_mult (float): The multiplier for the take-profit level.
        sl_mult (float): The multiplier for the stop-loss level.

    Returns:
        Tuple[float, float]: A tuple of (take_profit, stop_loss).
    """
    if not math.isfinite(entry_px) or not math.isfinite(atr) or atr <= 0:
        log.warning("Invalid bracket inputs: entry_px=%s atr=%s", entry_px, atr)
        return entry_px, entry_px

    tp = entry_px + tp_mult * atr
    sl = entry_px - sl_mult * atr

    if sl >= entry_px or tp <= entry_px:
        log.debug("Sanity correction: tp=%s sl=%s entry=%s", tp, sl, entry_px)
        tp, sl = entry_px * 1.01, entry_px * 0.99

    log.info(
        "Bracket computed: entry=%.2f atr=%.2f → tp=%.2f sl=%.2f", entry_px, atr, tp, sl
    )
    return round(tp, 2), round(sl, 2)
