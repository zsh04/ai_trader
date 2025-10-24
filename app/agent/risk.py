def exceeds_concentration(
    notional: float, equity: float, threshold: float = 0.5
) -> bool:
    return (equity > 0) and (notional / equity > threshold)
