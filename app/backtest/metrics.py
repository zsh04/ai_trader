# app/backtest/metrics.py
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from loguru import logger

TRADING_DAYS = 252


# -------- Data classes --------
@dataclass
class EquityMetrics:
    start: pd.Timestamp
    end: pd.Timestamp
    periods: int
    cagr: float
    total_return: float
    vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    max_dd_len: int
    mar: float


@dataclass
class TradeMetrics:
    n_trades: int
    win_rate: float
    avg_pnl: float
    avg_win: float
    avg_loss: float
    payoff: float
    expectancy: float
    best: float
    worst: float
    gross_profit: float
    gross_loss: float


# -------- Internals --------
def _to_returns(curve: pd.Series) -> pd.Series:
    s = curve.astype(float).dropna()
    if s.empty:
        return pd.Series(dtype=float)
    return s.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)


def _annualize_returns(
    mean_ret: float, std_ret: float, periods_per_year: int
) -> Tuple[float, float]:
    return mean_ret * periods_per_year, std_ret * math.sqrt(periods_per_year)


def _cagr(equity: pd.Series) -> float:
    s = equity.astype(float).dropna()
    if len(s) < 2:
        return 0.0
    # clamp very short backtests to avoid extreme annualization
    elapsed_years = max(0.25, (s.index[-1] - s.index[0]).days / 365.25)
    start_val = float(s.iloc[0])
    end_val = float(s.iloc[-1])
    if start_val <= 0:
        return 0.0
    return (end_val / start_val) ** (1.0 / elapsed_years) - 1.0


def _drawdown_curve(curve: pd.Series) -> Tuple[pd.Series, float, int]:
    s = curve.astype(float).dropna()
    if s.empty:
        return pd.Series(dtype=float), 0.0, 0
    cummax = s.cummax()
    dd = s / cummax - 1.0
    max_dd = float(dd.min())

    # Longest drawdown duration (consecutive dd < 0)
    mask = (dd < 0).to_numpy()
    max_run = run = 0
    for m in mask:
        if m:
            run += 1
            if run > max_run:
                max_run = run
        else:
            run = 0
    return dd, max_dd, int(max_run)


# -------- Public API --------
def equity_stats(
    equity_df: pd.DataFrame,
    *,
    use_mtm: bool = True,
    periods_per_year: int = TRADING_DAYS,
    risk_free_rate: float = 0.0,
) -> EquityMetrics:
    """
    Compute equity metrics from an equity curve.

    equity_df: DataFrame indexed by datetime, columns include 'equity' and optionally 'equity_mtm'.
    risk_free_rate: annual risk-free rate used to compute excess return in Sharpe.
    """
    col = "equity_mtm" if use_mtm and "equity_mtm" in equity_df.columns else "equity"
    curve = equity_df[col].astype(float).dropna()
    if not curve.index.is_monotonic_increasing:
        logger.warning("[metrics] equity index not monotonic; sorting by index")
        curve = curve.sort_index()
    if len(curve) < 50:
        logger.debug(
            "[metrics] short series (n={}) — stats may be unstable", len(curve)
        )
    if curve.empty:
        return EquityMetrics(
            pd.Timestamp(0), pd.Timestamp(0), 0, 0, 0, 0, 0, 0, 0, 0, 0
        )

    rets = _to_returns(curve)
    # convert annual risk-free to per-period (simple) and subtract from returns
    rf_per_period = float(risk_free_rate) / float(periods_per_year)
    if rf_per_period != 0.0:
        rets = rets - rf_per_period
    mean = float(rets.mean())
    std = float(rets.std(ddof=0))
    ann_mean, ann_std = _annualize_returns(mean, std, periods_per_year)
    sharpe = ann_mean / ann_std if ann_std > 0 else 0.0

    neg = rets[rets < 0]
    downs = float(neg.std(ddof=0)) if len(neg) else 0.0
    sortino = ann_mean / (downs * math.sqrt(periods_per_year)) if downs > 0 else 0.0

    _, max_dd, max_dd_len = _drawdown_curve(curve)
    total_ret = float(curve.iloc[-1] / curve.iloc[0] - 1.0)
    cagr = _cagr(curve)
    if max_dd < 0:
        mar_raw = cagr / abs(max_dd) if abs(max_dd) > 0 else 0.0
        mar = min(mar_raw, 100.0)
    else:
        mar = 0.0

    logger.debug(
        "[metrics] {}→{} n={} cagr={:.4f} tot={:.4f} vol={:.4f} sharpe={:.3f} sortino={:.3f} maxDD={:.4f} len={} mar={:.3f}",
        curve.index[0],
        curve.index[-1],
        len(curve),
        cagr,
        total_ret,
        ann_std,
        sharpe,
        sortino,
        max_dd,
        max_dd_len,
        mar,
    )

    return EquityMetrics(
        start=curve.index[0],
        end=curve.index[-1],
        periods=len(curve),
        cagr=cagr,
        total_return=total_ret,
        vol=ann_std,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        max_dd_len=max_dd_len,
        mar=mar,
    )


def trade_stats(trades: List[Dict[str, Any]]) -> TradeMetrics:
    if not trades:
        return TradeMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    closed = [t for t in trades if "pnl" in t]
    if not closed:
        return TradeMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    pnls = np.array([float(t.get("pnl", 0.0)) for t in closed], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    n = len(pnls)
    win_rate = float(len(wins)) / n if n else 0.0
    avg_pnl = float(pnls.mean()) if n else 0.0
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    payoff = (avg_win / abs(avg_loss)) if (avg_win > 0 and avg_loss < 0) else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    best = float(pnls.max()) if n else 0.0
    worst = float(pnls.min()) if n else 0.0
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(losses.sum()) if len(losses) else 0.0

    return TradeMetrics(
        n_trades=n,
        win_rate=win_rate,
        avg_pnl=avg_pnl,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff=payoff,
        expectancy=expectancy,
        best=best,
        worst=worst,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
    )


def summarize(
    backtest_result: Dict[str, Any],
    *,
    use_mtm: bool = True,
    periods_per_year: int = TRADING_DAYS,
) -> Dict[str, Any]:
    eq = backtest_result.get("equity")
    tr = backtest_result.get("trades", [])
    eqm = equity_stats(eq, use_mtm=use_mtm, periods_per_year=periods_per_year)
    tm = trade_stats(tr)
    logger.debug("[metrics] summary built: equity & trades")
    return {"equity": asdict(eqm), "trades": asdict(tm)}


def drawdown_series(equity_df: pd.DataFrame, *, use_mtm: bool = True) -> pd.Series:
    col = "equity_mtm" if use_mtm and "equity_mtm" in equity_df.columns else "equity"
    s = equity_df[col].astype(float).dropna()
    if s.empty:
        return pd.Series(dtype=float)
    return s / s.cummax() - 1.0
