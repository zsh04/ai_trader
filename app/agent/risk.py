"""Risk management primitives: concentration and exposure checks."""

from loguru import logger


def exceeds_concentration(
    notional: float, equity: float, threshold: float = 0.5
) -> bool:
    """
    Checks if notional exposure exceeds a given threshold fraction of equity.

    Args:
        notional (float): The notional value of the position.
        equity (float): The total equity.
        threshold (float): The concentration threshold.

    Returns:
        bool: True if the concentration is exceeded, False otherwise.
    """
    if equity <= 0:
        logger.warning("Invalid equity value (<=0) in concentration check.")
        return False

    ratio = notional / equity

    if ratio > threshold:
        logger.warning("Concentration exceeded: {:.2%} > {:.2%}", ratio, threshold)
        return True
    return False
