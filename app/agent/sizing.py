def position_size(equity: float, risk_pct: float, atr: float, stop_atr_mult: float = 1.0):
    risk_amt = equity * risk_pct
    if atr <= 0:
        return 0
    return max(int(risk_amt / (atr * stop_atr_mult)), 0)
