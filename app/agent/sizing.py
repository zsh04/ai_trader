"""Position sizing logic — calculates shares/contracts per trade based on risk budget and volatility."""
import logging

logger = logging.getLogger(__name__)

def position_size(
    equity: float,
    risk_pct: float,
    atr: float,
    stop_atr_mult: float = 1.0,
) -> int:
    """Compute trade size based on ATR-derived stop distance.

    Args:
        equity: Total account equity in dollars.
        risk_pct: Fraction (0–1) of equity to risk per trade.
        atr: Average True Range (volatility proxy).
        stop_atr_mult: Stop-loss multiple of ATR.

    Returns:
        Integer number of shares/contracts to trade.
    """
    if equity <= 0:
        logger.warning("Invalid equity (<=0) for sizing.")
        return 0
    if risk_pct <= 0 or atr <= 0 or stop_atr_mult <= 0:
        logger.debug("Sizing inputs below threshold: risk_pct=%s atr=%s stop_mult=%s", risk_pct, atr, stop_atr_mult)
        return 0

    risk_amt = equity * risk_pct
    raw_size = risk_amt / (atr * stop_atr_mult)
    size = max(int(raw_size), 0)

    logger.info(
        "Position size computed: equity=%.2f risk_pct=%.3f atr=%.4f stop_mult=%.2f size=%d",
        equity, risk_pct, atr, stop_atr_mult, size,
    )

    return size