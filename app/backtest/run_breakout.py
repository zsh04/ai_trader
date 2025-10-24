from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.backtest.engine import Costs, backtest_long_only
from app.backtest.metrics import metrics
from app.backtest.model import BetaWinrate
from app.providers.yahoo_provider import get_history_daily
from app.strats.breakout import BreakoutParams, generate_signals


def _try_backtest(engine_fn, base_kwargs: dict):
    """
    Call backtest_long_only with a sequence of likely signatures to avoid flatline
    due to missing initial capital / fractional share flags across versions.
    """
    trials = [
        {},  # as-is
        {"initial_equity": 100_000.0},
        {"init_equity": 100_000.0},
        {"starting_equity": 100_000.0},
        {"capital": 100_000.0},
        {"initial_equity": 100_000.0, "allow_fractional": True},
        {"initial_equity": 100_000.0, "fractional": True},
        {"initial_equity": 100_000.0, "integer_shares": False},
        {"init_equity": 100_000.0, "allow_fractional": True},
        {"init_equity": 100_000.0, "integer_shares": False},
        {"capital": 100_000.0, "integer_shares": False},
    ]
    for extra in trials:
        try:
            return engine_fn(**{**base_kwargs, **extra}), extra
        except TypeError:
            continue
    # final attempt: run as-is
    return engine_fn(**base_kwargs), {}


def run(
    symbol: str,
    start: str,
    end: str | None,
    params_kwargs: dict,
    slippage_bps: float | None = None,
    fee_per_share: float | None = None,
    risk_frac_override: float | None = None,
    debug: bool = False,
    debug_signals: bool = False,
    debug_entries: bool = False,
):
    start_dt = pd.to_datetime(start).date()
    end_dt = pd.to_datetime(end).date() if end else datetime.now(UTC).date()
    df = get_history_daily(symbol, start_dt, end_dt)
    df = df.dropna().copy()

    p = BreakoutParams(**params_kwargs)
    sig = generate_signals(df, asdict(p))
    # Use normalized OHLC from signals for the engine (ensures lowercase open/high/low/close)
    if all(c in sig.columns for c in ["open", "high", "low", "close"]):
        df_engine = sig[["open", "high", "low", "close"]].copy()
    else:
        df_engine = df
    # Convert persistent states to one-bar events
    entry_state = sig["long_entry"].astype(bool)
    exit_state = sig["long_exit"].astype(bool)

    entry_event = entry_state & ~entry_state.shift(1, fill_value=False)
    exit_event = exit_state & ~exit_state.shift(1, fill_value=False)

    # If engine executes next-bar by design and we are NOT entering on break bar,
    # shift the edge events to the following bar.
    if not getattr(p, "enter_on_break_bar", False):
        entry_event = entry_event.shift(1, fill_value=False)
        exit_event = exit_event.shift(1, fill_value=False)

    # Sanity: keep indexes aligned and dtype boolean
    assert entry_event.index.equals(df_engine.index)
    assert exit_event.index.equals(df_engine.index)
    entry_event = entry_event.astype(bool)
    exit_event = exit_event.astype(bool)

    # Sanity logs
    print(f"[DEBUG] entry_event={entry_event.sum()} exit_event={exit_event.sum()}")

    # Also build DatetimeIndex of event bars (some engines expect indices)
    entry_idx = entry_event[entry_event].index
    exit_idx = exit_event[exit_event].index
    if debug:
        print(f"[DEBUG] entry_idx={len(entry_idx)} exit_idx={len(exit_idx)}")

    # --- Optional verbose diagnostics for signals ---
    try:
        entries_mask = sig.get("long_entry", pd.Series(False, index=df.index)).astype(
            bool
        )
        exits_mask = sig.get("long_exit", pd.Series(False, index=df.index)).astype(bool)
        entries_idx = list(sig.index[entries_mask])
        # exits_idx = list(sig.index[exits_mask])
        if debug_entries:
            first_n = min(5, len(entries_idx))
            last_n = min(5, len(entries_idx))
            if first_n > 0:
                print(
                    f"[DEBUG] first entries ({first_n}): {[str(i) for i in entries_idx[:first_n]]}"
                )
            if last_n > 0:
                print(
                    f"[DEBUG] last entries ({last_n}):  {[str(i) for i in entries_idx[-last_n:]]}"
                )
        if debug_signals:
            cols_dbg_all = [
                c
                for c in [
                    "open",
                    "high",
                    "low",
                    "close",
                    "hh",
                    "hh_buf",
                    "ema",
                    "atr",
                    "atr_ok",
                    "trail_stop",
                    "trend_ok",
                    "trigger",
                    "long_entry",
                    "long_exit",
                ]
                if c in sig.columns
            ]
            try:
                sig.tail(200)[cols_dbg_all].to_csv(f"signals_tail_{symbol}.csv")
                sig.loc[entries_mask | exits_mask, cols_dbg_all].tail(200).to_csv(
                    f"signals_events_{symbol}.csv"
                )
                print(
                    f"[DEBUG] Saved signals_tail_{symbol}.csv and signals_events_{symbol}.csv"
                )
            except Exception as e_dump:
                print(f"[DEBUG] signal dump failed: {e_dump}")
    except Exception as e_diag:
        print(f"[DEBUG] signal verbose-diagnostics failed: {e_diag}")

    # --- Diagnostics: signal flow & optional CSV dump ---
    try:
        entries = int(sig["long_entry"].sum())
        exits = int(sig["long_exit"].sum())
        print(f"[DEBUG] entries={entries} exits={exits} rows={len(sig)}")
        if entries == 0 or debug_signals:
            cols_dbg = [
                c
                for c in [
                    "close",
                    "high",
                    "hh",
                    "hh_buf",
                    "ema",
                    "trend_ok",
                    "trigger",
                    "long_entry",
                    "long_exit",
                ]
                if c in sig.columns
            ]
            tail = sig[cols_dbg].tail(50) if cols_dbg else sig.tail(50)
            dbg_path = f"signals_debug_tail_{symbol}.csv"
            try:
                tail.to_csv(dbg_path)
                print(f"[DEBUG] Saved last 50-bar signal snapshot -> {dbg_path}")
            except Exception as e_dump:
                print(f"[DEBUG] tail dump failed: {e_dump}")
    except Exception as e:
        print(f"[DEBUG] signal diagnostics failed: {e}")

    beta = BetaWinrate()
    default_risk = (
        0.01 * beta.kelly_fraction() / max(beta.fmax, 1e-6) if beta.fmax > 0 else 0.01
    )

    bt_kwargs = dict(
        df=df_engine,
        entry=entry_event,  # pass one-bar boolean events (Series for engine .iloc)
        exit_=exit_event,  # pass one-bar boolean events
        atr=sig["atr"],
        entry_price=p.entry_price,
        atr_mult=p.atr_mult,
        risk_frac=(
            risk_frac_override if risk_frac_override is not None else default_risk
        ),
        costs=Costs(
            slippage_bps=slippage_bps if slippage_bps is not None else 1.0,
            fee_per_share=fee_per_share if fee_per_share is not None else 0.0,
        ),
        model=beta,
    )
    bt_kwargs["min_notional"] = args.min_notional
    res, used_extra = _try_backtest(backtest_long_only, bt_kwargs)
    if used_extra:
        print(f"[DEBUG] backtest_long_only extra kwargs applied: {used_extra}")

    try:
        trades_obj = res.get("trades")
        trades_len = len(trades_obj) if hasattr(trades_obj, "__len__") else -1
        print(f"[DEBUG] trades_len={trades_len}")
        if trades_len > 0:
            preview = trades_obj[: min(3, trades_len)]
            print("[DEBUG] first_trades:", preview)
    except Exception as e_tr:
        print(f"[DEBUG] trades introspection failed: {e_tr}")

    try:
        print(f"[DEBUG] res keys: {list(res.keys())}")
        eq = res.get("equity")
        if eq is not None and hasattr(eq, "diff"):
            moved = float(np.nansum(np.abs(eq.diff().to_numpy())))
            print(f"[DEBUG] equity moved (abs sum of diffs): {moved:.6f}")
    except Exception as e_keys:
        print(f"[DEBUG] res introspection failed: {e_keys}")

    # --- Equity flatline diagnostics ---
    try:
        eq = res.get("equity")
        flat = False
        if eq is not None and hasattr(eq, "diff"):
            try:
                if isinstance(eq, pd.DataFrame):
                    moved = float(eq.diff().abs().to_numpy().sum())
                else:
                    moved = float(eq.diff().abs().sum())
                flat = moved == 0.0
            except Exception as e_calc:
                print(f"[DEBUG] equity move calc failed: {e_calc}")
                flat = False
        if flat or debug_signals:
            # How many entries had invalid ATR (using atr_ok if available)
            invalid_atr = None
            if {"long_entry", "atr_ok"}.issubset(sig.columns):
                invalid_atr = int((sig["long_entry"] & (~sig["atr_ok"])).sum())
                print(f"[DEBUG] entries with invalid ATR: {invalid_atr}")
            elif {"long_entry", "atr"}.issubset(sig.columns):
                invalid_atr = int((sig["long_entry"] & (~sig["atr"].gt(0))).sum())
                print(f"[DEBUG] entries with invalid ATR(alt): {invalid_atr}")
            # Dump last 100 bars of relevant columns
            cols_dbg2 = [
                c
                for c in [
                    "open",
                    "high",
                    "low",
                    "close",
                    "hh",
                    "hh_buf",
                    "ema",
                    "atr",
                    "atr_ok",
                    "trail_stop",
                    "trend_ok",
                    "trigger",
                    "long_entry",
                    "long_exit",
                ]
                if c in sig.columns
            ]
            snap = sig[cols_dbg2].tail(100) if cols_dbg2 else sig.tail(100)
            dbg2_path = f"signals_flat_debug_{symbol}.csv"
            snap.to_csv(dbg2_path)
            print(f"[DEBUG] Equity flat; saved snapshot -> {dbg2_path}")
    except Exception as e:
        print(f"[DEBUG] equity-flat diagnostics failed: {e}")

    m = metrics(res["equity"])
    print(f"[{symbol}] metrics:", {k: round(v, 4) for k, v in m.items()})
    out = f"backtest_{symbol}.csv"
    res["equity"].to_csv(out)
    print(f"Saved equity curve -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Run breakout backtest with configurable parameters"
    )
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", default=None)

    # --- Strategy Parameters ---
    ap.add_argument("--lookback", type=int, help="Breakout lookback window length")
    ap.add_argument(
        "--ema", dest="ema_fast", type=int, help="EMA length for trend filter"
    )
    ap.add_argument("--atr", dest="atr_len", type=int, help="ATR lookback period")
    ap.add_argument(
        "--atr-mult",
        dest="atr_mult",
        type=float,
        help="ATR multiple for stop placement",
    )
    ap.add_argument(
        "--hold-bars",
        dest="hold_bars",
        type=int,
        help="Bars to hold before auto-exit (0 disables)",
    )
    ap.add_argument(
        "--entry-price",
        dest="entry_price",
        choices=["close", "next_open"],
        help="Entry price mode",
    )

    ap.add_argument(
        "--use-ema-filter",
        dest="use_ema_filter",
        action="store_true",
        default=None,
        help="Require close > EMA for entry signal",
    )
    ap.add_argument(
        "--no-ema-filter",
        dest="use_ema_filter",
        action="store_false",
        help="Disable EMA trend filter for entries",
    )

    ap.add_argument(
        "--exit-on-ema-break",
        dest="exit_on_ema_break",
        action="store_true",
        default=None,
        help="Exit on EMA cross-down event",
    )
    ap.add_argument(
        "--no-exit-on-ema-break",
        dest="exit_on_ema_break",
        action="store_false",
        help="Disable exit on EMA break",
    )

    ap.add_argument(
        "--breakout-buffer-pct",
        dest="breakout_buffer_pct",
        type=float,
        help="Breakout buffer percentage above high-high level (e.g., 0.001 = 0.1%)",
    )
    ap.add_argument(
        "--min-break-valid",
        dest="min_break_valid",
        type=int,
        help="Override min_periods for breakout window",
    )

    ap.add_argument(
        "--confirm-with-high",
        dest="confirm_with_high",
        action="store_true",
        default=None,
        help="Confirm breakout using high >= HH (default True)",
    )
    ap.add_argument(
        "--no-confirm-with-high",
        dest="confirm_with_high",
        action="store_false",
        help="Confirm breakout using close >= HH",
    )
    ap.add_argument(
        "--use-close-breakout",
        dest="use_close_for_breakout",
        action="store_true",
        default=None,
        help="Use rolling max of CLOSE for HH instead of HIGH",
    )
    ap.add_argument(
        "--enter-on-break-bar",
        dest="enter_on_break_bar",
        action="store_true",
        default=None,
        help="Enter on the same bar as the breakout (no shift)",
    )

    # --- Backtest / Risk Parameters ---
    ap.add_argument(
        "--slippage-bps",
        dest="slippage_bps",
        type=float,
        help="Slippage in basis points",
    )
    ap.add_argument(
        "--fee-per-share", dest="fee_per_share", type=float, help="Fee per share traded"
    )
    ap.add_argument(
        "--risk-frac",
        type=float,
        default=0.03,
        help="Risk fraction per trade (default: 0.03 = 3%)",
    )
    ap.add_argument(
        "--min-notional",
        dest="min_notional",
        type=float,
        default=100.0,
        help="Minimum notional value per trade (default: 100.0)",
    )

    # --- Debug / Diagnostics ---
    ap.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        default=False,
        help="Enable verbose diagnostics",
    )
    ap.add_argument(
        "--debug-signals",
        dest="debug_signals",
        action="store_true",
        default=False,
        help="Dump signal snapshots",
    )
    ap.add_argument(
        "--debug-entries",
        dest="debug_entries",
        action="store_true",
        default=False,
        help="Dump first/last entry bars",
    )

    args = ap.parse_args()

    # Build kwargs for BreakoutParams
    candidate_keys = [
        "lookback",
        "ema_fast",
        "atr_len",
        "atr_mult",
        "hold_bars",
        "entry_price",
        "exit_on_ema_break",
        "use_ema_filter",
        "breakout_buffer_pct",
        "min_break_valid",
        "confirm_with_high",
        "use_close_for_breakout",
        "enter_on_break_bar",
    ]
    raw_kwargs = {
        k: getattr(args, k) for k in candidate_keys if getattr(args, k) is not None
    }
    # Filter out any keys not supported by BreakoutParams (handles version drift)
    try:
        allowed_keys = set(getattr(BreakoutParams, "__annotations__", {}).keys())
    except Exception:
        allowed_keys = set()
    params_kwargs = {k: v for k, v in raw_kwargs.items() if k in allowed_keys}

    run(
        args.symbol,
        args.start,
        args.end,
        params_kwargs=params_kwargs,
        slippage_bps=args.slippage_bps,
        fee_per_share=args.fee_per_share,
        risk_frac_override=args.risk_frac,
        debug=args.debug,
        debug_signals=args.debug_signals or args.debug,
        debug_entries=args.debug_entries or args.debug,
    )
