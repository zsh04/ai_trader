from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Costs:
    slippage_bps: float = 1.0  # 1bp
    fee_per_share: float = 0.0


def _as_series(x):
    import pandas as pd

    return x.iloc[:, 0] if isinstance(x, pd.DataFrame) else x


def backtest_long_only(
    df: pd.DataFrame,
    entry: pd.Series,
    exit_: pd.Series,
    atr: pd.Series,
    entry_price: str = "close",  # "close" or "next_open"
    atr_mult: float = 2.0,
    risk_frac: float = 0.03,  # baseline fraction of equity risked if allowed by model
    costs: Costs | None = None,
    model=None,  # BetaWinrate or None
    init_equity: float = 100_000.0,
    # New optional knobs (compatible with various runners)
    initial_equity: float | None = None,
    starting_equity: float | None = None,
    capital: float | None = None,
    integer_shares: bool | None = None,
    allow_fractional: bool | None = None,
    min_shares: float = 1e-6,
    min_notional: float = 100.0,
    **kwargs,
) -> dict:
    """
    Simple 1-position engine: enter on signal, position size from ATR, exit on exit_ or stop.
    Assumes daily bars. Fills: at close or next open.
    """
    # Normalize capital & share handling knobs
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

    # Coerce to true Series once (avoids single-element Series warnings) and use .iat for scalars
    px_open = _as_series(df["open"])
    px_close = _as_series(df["close"])
    px_low = _as_series(df["low"])
    atr = _as_series(atr)

    equity = float(init_equity)
    in_pos = False
    entry_px = 0.0
    stop_px = 0.0
    shares = 0.0

    equity_curve = []
    trades = []

    # include an initial snapshot at index 0
    if len(df) > 0:
        equity_curve.append((df.index[0], equity))

    for i in range(1, len(df)):
        date = df.index[i]

        # mark-to-market (simple; extend to MTM unrealized PnL if desired)
        equity_curve.append((date, equity))

        # exit logic (stop or rule) — scalar-safe booleans
        if in_pos:
            low_i = float(px_low.iat[i])
            exit_hit = bool(exit_.iloc[i])  # exit_ is already a boolean Series
            stop_hit = bool(low_i <= float(stop_px))

            if exit_hit or stop_hit:
                exit_px = float(px_close.iat[i])
                # slippage
                exit_px *= 1 - costs.slippage_bps / 1e4
                if stop_hit:
                    exit_px = min(exit_px, float(stop_px))

                pnl = (exit_px - float(entry_px)) * float(shares)
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

        # entry logic
        if not in_pos and bool(entry.iloc[i]):
            # Model gate: allow first trade even if model.allow() is conservative
            model_ok = (
                (model is None)
                or getattr(model, "allow", lambda: True)()
                or (len(trades) == 0)
            )
            if model_ok:
                # fill price
                if entry_price == "close":
                    fill_px = float(px_close.iat[i])
                else:  # "next_open"
                    fill_px = (
                        float(px_open.iat[i + 1])
                        if (i + 1) < len(df)
                        else float(px_close.iat[i])
                    )
                fill_px *= 1 + costs.slippage_bps / 1e4

                rf = float(risk_frac)
                # Clamp: positive and not absurd (upper bound is just defensive)
                if not (rf > 0.0) or not (rf <= 0.25):
                    # If runner passed 0/NaN/negative or >25%, fall back to 3%
                    rf = 0.03

                # position sizing
                risk_dollar = float(equity) * rf
                this_atr = max(1e-6, float(atr.iat[i]))
                stop_px = float(fill_px) - float(atr_mult) * this_atr
                risk_per_share = max(1e-6, float(fill_px) - stop_px)
                raw_shares = risk_dollar / risk_per_share
                if fractional_ok:
                    min_shares_by_notional = float(min_notional) / max(
                        1e-6, float(fill_px)
                    )
                    shares = max(float(raw_shares), min_shares_by_notional)
                else:
                    shares = float(int(max(0.0, raw_shares)))

                if shares > 0.0:
                    # fees (approx)
                    equity -= shares * costs.fee_per_share
                    entry_px = fill_px  # already float
                    in_pos = True
                    trades.append(
                        {
                            "date_in": date,
                            "in": entry_px,
                            "shares": shares,
                            "stop": stop_px,
                        }
                    )

        # update model after a closed trade (handled above)
        if (
            model
            and trades
            and "pnl" in trades[-1]
            and trades[-1].get("_accounted") is not True
        ):
            model.update(trades[-1]["pnl"] > 0)
            trades[-1]["_accounted"] = True

    curve = pd.DataFrame(equity_curve, columns=["date", "equity"]).set_index("date")
    return {"equity": curve, "trades": trades}
