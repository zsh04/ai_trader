from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd


@dataclass
class Costs:
    """
    Per-trade cost assumptions.

    Attributes:
        slippage_bps (float): Per-fill slippage in basis points.
        fee_per_share (float): Fixed fee per share.
    """

    slippage_bps: float = 1.0
    fee_per_share: float = 0.0


_DEF_MIN_EPS = 1e-6


def _as_series(x: pd.Series | pd.DataFrame) -> pd.Series:
    """
    Returns the first column of a DataFrame or the Series itself.

    Args:
        x (pd.Series | pd.DataFrame): The input Series or DataFrame.

    Returns:
        pd.Series: The first column of the DataFrame or the Series itself.
    """
    return x.iloc[:, 0] if isinstance(x, pd.DataFrame) else x


def _align_series(
    s: pd.Series | pd.DataFrame, index: pd.Index, *, fill: Any = 0
) -> pd.Series:
    """
    Aligns a Series to a given index.

    Args:
        s (pd.Series | pd.DataFrame): The Series or DataFrame to align.
        index (pd.Index): The index to align to.
        fill (Any): The value to fill missing values with.

    Returns:
        pd.Series: The aligned Series.
    """
    ser = _as_series(s)
    if not ser.index.equals(index):
        ser = ser.reindex(index)
    return ser.fillna(fill)


def backtest_long_only(
    df: pd.DataFrame,
    entry: pd.Series,
    exit_: pd.Series,
    atr: pd.Series,
    entry_price: str = "close",
    atr_mult: float = 2.0,
    risk_frac: float = 0.03,
    costs: Costs | None = None,
    mark_to_market: bool = True,
    mtm_price: str = "close",
    model=None,
    init_equity: float = 100_000.0,
    initial_equity: float | None = None,
    starting_equity: float | None = None,
    capital: float | None = None,
    integer_shares: bool | None = None,
    allow_fractional: bool | None = None,
    min_shares: float = _DEF_MIN_EPS,
    min_notional: float = 100.0,
    **kwargs,
) -> Dict[str, Any]:
    """
    A minimal long-only backtest engine.

    Args:
        df (pd.DataFrame): A DataFrame with OHLC data.
        entry (pd.Series): A Series of entry signals.
        exit_ (pd.Series): A Series of exit signals.
        atr (pd.Series): A Series of ATR values.
        entry_price (str): The entry price to use.
        atr_mult (float): The ATR multiplier for the stop loss.
        risk_frac (float): The fraction of equity to risk per trade.
        costs (Costs | None): The cost model to use.
        mark_to_market (bool): Whether to mark to market.
        mtm_price (str): The price to use for mark-to-market.
        model: An optional model to use for gating trades.
        init_equity (float): The initial equity.
        initial_equity (float | None): The initial equity.
        starting_equity (float | None): The initial equity.
        capital (float | None): The initial equity.
        integer_shares (bool | None): Whether to use integer shares.
        allow_fractional (bool | None): Whether to allow fractional shares.
        min_shares (float): The minimum number of shares to trade.
        min_notional (float): The minimum notional value to trade.
        **kwargs: Additional keyword arguments.

    Returns:
        Dict[str, Any]: A dictionary with the backtest results.
    """
    if initial_equity is not None:
        init_equity = float(initial_equity)
    elif starting_equity is not None:
        init_equity = float(starting_equity)
    elif capital is not None:
        init_equity = float(capital)

    fractional_ok = True
    if integer_shares is not None:
        fractional_ok = not bool(integer_shares)
    if allow_fractional is not None:
        fractional_ok = bool(allow_fractional)

    if costs is None:
        costs = Costs()

    atr_mult = float(atr_mult)
    if atr_mult <= 0:
        atr_mult = 2.0
    rf = float(risk_frac)
    if not (rf > 0.0) or not (rf <= 0.25):
        rf = 0.03

    idx = df.index
    px_open = _align_series(df["open"], idx)
    px_high = _align_series(df["high"], idx)
    px_close = _align_series(df["close"], idx)
    px_low = _align_series(df["low"], idx)
    atr = _align_series(atr, idx, fill=_DEF_MIN_EPS).astype(float)
    entry = _align_series(entry, idx, fill=False).astype(bool)
    exit_ = _align_series(exit_, idx, fill=False).astype(bool)

    equity = float(init_equity)
    in_pos = False
    entry_px = 0.0
    stop_px = 0.0
    shares = 0.0

    equity_curve: list[tuple[pd.Timestamp, float, float]] = []
    trades: list[Dict[str, Any]] = []

    for i in range(1, len(idx)):
        date = idx[i]

        if in_pos:
            low_i = float(px_low.iat[i])
            exit_hit = bool(exit_.iat[i])
            stop_hit = bool(low_i <= float(stop_px))

            if exit_hit or stop_hit:
                exit_px = float(px_close.iat[i])
                exit_px *= 1 - costs.slippage_bps / 1e4
                if stop_hit:
                    exit_px = min(exit_px, float(stop_px))

                fee = float(shares) * float(costs.fee_per_share)
                pnl = (exit_px - float(entry_px)) * float(shares) - fee
                equity += pnl

                trades.append(
                    {
                        "date_out": date,
                        "in": float(entry_px),
                        "out": exit_px,
                        "qty": float(shares),
                        "pnl": float(pnl),
                        "reason": "STOP" if stop_hit else "EXIT",
                    }
                )
                in_pos = False
                shares = 0.0

        if (not in_pos) and bool(entry.iat[i]):
            model_ok = (
                (model is None)
                or getattr(model, "allow", lambda: True)()
                or (len(trades) == 0)
            )
            if model_ok:
                if entry_price == "close":
                    fill_px = float(px_close.iat[i])
                else:
                    next_i = i + 1
                    fill_px = (
                        float(px_open.iat[next_i])
                        if next_i < len(idx)
                        else float(px_close.iat[i])
                    )
                fill_px *= 1 + costs.slippage_bps / 1e4

                risk_dollar = float(equity) * rf
                this_atr = max(_DEF_MIN_EPS, float(atr.iat[i]))
                stop_px = float(fill_px) - float(atr_mult) * this_atr
                risk_per_share = max(_DEF_MIN_EPS, float(fill_px) - float(stop_px))
                raw_shares = risk_dollar / risk_per_share

                if fractional_ok:
                    min_shares_by_notional = float(min_notional) / max(
                        _DEF_MIN_EPS, float(fill_px)
                    )
                    shares = max(
                        float(raw_shares), float(min_shares), min_shares_by_notional
                    )
                else:
                    shares = float(int(max(0.0, raw_shares)))

                if shares > 0.0:
                    equity -= shares * float(costs.fee_per_share)
                    entry_px = float(fill_px)
                    in_pos = True
                    trades.append(
                        {
                            "date_in": date,
                            "in": entry_px,
                            "shares": shares,
                            "stop": float(stop_px),
                        }
                    )

        if (
            model
            and trades
            and ("pnl" in trades[-1])
            and trades[-1].get("_accounted") is not True
        ):
            try:
                model.update(trades[-1]["pnl"] > 0)
            finally:
                trades[-1]["_accounted"] = True

        if mark_to_market and in_pos and shares > 0.0:
            if mtm_price == "mid":
                mtm_px = float((px_high.iat[i] + px_low.iat[i]) / 2.0)
            else:
                mtm_px = float(px_close.iat[i])
            unrealized = (mtm_px - float(entry_px)) * float(shares)
            equity_mtm = float(equity) + float(unrealized)
        else:
            equity_mtm = float(equity)
        equity_curve.append((date, float(equity), float(equity_mtm)))

    curve = pd.DataFrame(
        equity_curve, columns=["date", "equity", "equity_mtm"]
    ).set_index("date")
    return {"equity": curve, "trades": trades}
