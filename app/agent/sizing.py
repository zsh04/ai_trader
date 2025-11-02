"""Position sizing logic — calculates shares/contracts per trade based on risk budget and volatility."""

from loguru import logger


def position_size(
    equity: float,
    risk_pct: float,
    atr: float,
    stop_atr_mult: float = 1.0,
) -> int:
    """
    Computes the trade size based on an ATR-derived stop distance.

    Args:
        equity (float): The total account equity in dollars.
        risk_pct (float): The fraction of equity to risk per trade (0-1).
        atr (float): The Average True Range (ATR) as a volatility proxy.
        stop_atr_mult (float): The stop-loss as a multiple of ATR.

    Returns:
        int: The number of shares or contracts to trade.
    """
    if equity <= 0:
        logger.warning("Invalid equity (<=0) for sizing.")
        return 0
    if risk_pct <= 0 or atr <= 0 or stop_atr_mult <= 0:
        logger.debug(
            "Sizing inputs below threshold: risk_pct={} atr={} stop_mult={}",
            risk_pct,
            atr,
            stop_atr_mult,
        )
        return 0

    risk_amt = equity * risk_pct
    raw_size = risk_amt / (atr * stop_atr_mult)
    size = max(int(raw_size), 0)

    logger.info(
        "Position size computed: equity={:.2f} risk_pct={:.3f} atr={:.4f} stop_mult={:.2f} size={}",
        equity,
        risk_pct,
        atr,
        stop_atr_mult,
        size,
    )

    return size
