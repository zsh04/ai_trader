"""Risk management primitives: concentration and exposure checks."""
import logging
logger = logging.getLogger(__name__)

def exceeds_concentration(
    notional: float, equity: float, threshold: float = 0.5
) -> bool:
    """Return True if notional exposure exceeds the given threshold fraction of equity."""
    # Guard against invalid equity values
    if equity <= 0:
        logger.warning("Invalid equity value (<=0) in concentration check.")
        return False

    # Calculate the ratio of notional to equity
    ratio = notional / equity

    # Check if the ratio exceeds the threshold and log a warning if it does
    if ratio > threshold:
        logger.warning(f"Concentration exceeded: {ratio:.2%} > {threshold:.2%}")
        return True
    return False
