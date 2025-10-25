from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd


# --------------------------------------------------------------------------------------
# Cost model
# --------------------------------------------------------------------------------------
@dataclass
class Costs:
    """Per-trade cost assumptions.

    Attributes
    ----------
    slippage_bps : float
        Per-fill slippage in basis points (applied on both entry and exit).
    fee_per_share : float
        Fixed fee per share (applied on entry and exit).
    """

    slippage_bps: float = 1.0  # 1 bp per fill
    fee_per_share: float = 0.0


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
_DEF_MIN_EPS = 1e-6


def _as_series(x: pd.Series | pd.DataFrame) -> pd.Series:
    """Return the first column if a DataFrame else the Series itself."""
    return x.iloc[:, 0] if isinstance(x, pd.DataFrame) else x


def _align_series(s: pd.Series | pd.DataFrame, index: pd.Index, *, fill: Any = 0) -> pd.Series:
    """Coerce to a Series aligned to *index*.

    Ensures safe element access with `.iat` and avoids misalignment errors when
    comparing `DataFrame` and `Series` objects.
    """
    ser = _as_series(s)
    if not ser.index.equals(index):
        ser = ser.reindex(index)
    return ser.fillna(fill)


# --------------------------------------------------------------------------------------
# Backtest engine (long-only, 1 position)
# --------------------------------------------------------------------------------------

def backtest_long_only(
    df: pd.DataFrame,
    entry: pd.Series,
    exit_: pd.Series,
    atr: pd.Series,
    entry_price: str = "close",  # "close" or "next_open"
    atr_mult: float = 2.0,
    risk_frac: float = 0.03,  # fraction of equity risked
    costs: Costs | None = None,
    mark_to_market: bool = True,
    mtm_price: str = "close",
    model=None,  # object with .allow() and .update(win: bool) or None
    init_equity: float = 100_000.0,
    # Compatibility knobs used by some runners
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
    Minimal long-only backtest engine with ATR-based position sizing and a trailing stop.

    Parameters
    ----------
    df : DataFrame
        Must contain columns: `open`, `high`, `low`, `close` (case sensitive).
    entry, exit_ : Series[bool]
        Boolean signals aligned to `df.index`. `entry` opens a long. `exit_` closes it.
    atr : Series[float]
        Average True Range used for stop distance and sizing. Must be > 0.
    entry_price : {"close", "next_open"}
        Fill model for entries.
    atr_mult : float
        Multiplier on ATR to set the initial stop below the fill price.
    risk_frac : float
        Fraction of equity risked per trade (clamped to (0, 0.25]).
    costs : Costs | None
        Slippage and per-share fees. Slippage is applied on both entry and exit.
    mark_to_market : bool
        If True, report an equity curve with unrealized PnL marked each bar.
    mtm_price : {"close", "mid"}
        Price source for mark-to-market; `mid` uses (high+low)/2.
    model : Any | None
        Optional gate with `.allow()` and `.update(win: bool)` methods.

    Returns
    -------
    dict
        `{ "equity": DataFrame(date, equity), "trades": List[dict] }`.
    """

    # Normalize equity inputs
    if initial_equity is not None:
        init_equity = float(initial_equity)
    elif starting_equity is not None:
        init_equity = float(starting_equity)
    elif capital is not None:
        init_equity = float(capital)

    # Share discretization
    fractional_ok = True
    if integer_shares is not None:
        fractional_ok = not bool(integer_shares)
    if allow_fractional is not None:
        fractional_ok = bool(allow_fractional)

    if costs is None:
        costs = Costs()

    # Defensive parameter guards
    atr_mult = float(atr_mult)
    if atr_mult <= 0:
        atr_mult = 2.0
    rf = float(risk_frac)
    if not (rf > 0.0) or not (rf <= 0.25):
        rf = 0.03

    # Ensure all inputs are series aligned to df.index
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

        # -----------------
        # Exit checks first
        # -----------------
        if in_pos:
            low_i = float(px_low.iat[i])
            exit_hit = bool(exit_.iat[i])
            stop_hit = bool(low_i <= float(stop_px))

            if exit_hit or stop_hit:
                # Exit fill at close (with slippage). If stop was pierced, cap at stop.
                exit_px = float(px_close.iat[i])
                exit_px *= 1 - costs.slippage_bps / 1e4
                if stop_hit:
                    exit_px = min(exit_px, float(stop_px))

                # Commissions/fees on exit as well
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

        # --------------
        # Entry if flat
        # --------------
        if (not in_pos) and bool(entry.iat[i]):
            model_ok = (model is None) or getattr(model, "allow", lambda: True)() or (len(trades) == 0)
            if model_ok:
                # Determine entry fill
                if entry_price == "close":
                    fill_px = float(px_close.iat[i])
                else:  # next_open
                    next_i = i + 1
                    fill_px = (
                        float(px_open.iat[next_i]) if next_i < len(idx) else float(px_close.iat[i])
                    )
                # Entry slippage and entry fee
                fill_px *= 1 + costs.slippage_bps / 1e4

                # Risk-based sizing
                risk_dollar = float(equity) * rf
                this_atr = max(_DEF_MIN_EPS, float(atr.iat[i]))
                stop_px = float(fill_px) - float(atr_mult) * this_atr
                risk_per_share = max(_DEF_MIN_EPS, float(fill_px) - float(stop_px))
                raw_shares = risk_dollar / risk_per_share

                if fractional_ok:
                    min_shares_by_notional = float(min_notional) / max(_DEF_MIN_EPS, float(fill_px))
                    shares = max(float(raw_shares), float(min_shares), min_shares_by_notional)
                else:
                    shares = float(int(max(0.0, raw_shares)))

                if shares > 0.0:
                    # Apply entry fees immediately (reduces equity)
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

        # ----------------------
        # Post-trade model update
        # ----------------------
        if model and trades and ("pnl" in trades[-1]) and trades[-1].get("_accounted") is not True:
            try:
                model.update(trades[-1]["pnl"] > 0)
            finally:
                trades[-1]["_accounted"] = True

        # -----------------
        # Per-bar equity mark
        # -----------------
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

    curve = pd.DataFrame(equity_curve, columns=["date", "equity", "equity_mtm"]).set_index("date")
    return {"equity": curve, "trades": trades}
