from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import logging
import math
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Callable, Dict, Tuple

import numpy as np
import pandas as pd
from pandas import Timestamp

from app.backtest.engine import Costs, backtest_long_only
from app.backtest import metrics as bt_metrics
from app.backtest.model import BetaWinrate
from app.providers.yahoo_provider import get_history_daily
from app.strats.breakout import BreakoutParams, generate_signals

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
log = logging.getLogger(__name__)

def _setup_cli_logging(level: int = logging.INFO) -> None:
    """
    Idempotent CLI logging initializer. Keeps uvicorn/fastapi logs quiet when used as a script,
    and provides consistent formatting for CI logs.
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    else:
        root.setLevel(level)

def _roundish(x, ndigits=4):
    if isinstance(x, (float, np.floating)):
        if math.isfinite(float(x)):
            return round(float(x), ndigits)
        return str(x)  # inf / -inf
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, Timestamp):
        return x.isoformat()
    return str(x)

def _try_backtest(
    engine_fn: Callable[..., Dict[str, Any]],
    base_kwargs: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
    params_kwargs: Dict[str, Any],
    *,
    slippage_bps: float | None = None,
    fee_per_share: float | None = None,
    risk_frac_override: float | None = None,
    min_notional: float = 100.0,
    debug: bool = False,
    debug_signals: bool = False,
    debug_entries: bool = False,
) -> None:
    """
    Execute a long-only breakout backtest for a single symbol.
    """
    start_dt = pd.to_datetime(start).date()
    end_dt = pd.to_datetime(end).date() if end else datetime.now(UTC).date()

    log.info("Fetching daily history for %s: %s → %s", symbol, start_dt, end_dt)
    df = get_history_daily(symbol, start_dt, end_dt).dropna().copy()
    if df.empty:
        log.error("No history returned for %s in [%s, %s]. Check data provider/API keys.", symbol, start_dt, end_dt)
        return

    # Strategy params
    p = BreakoutParams(**params_kwargs)
    sig = generate_signals(df, asdict(p))

    # Engine OHLC input (ensure lowercase columns)
    if all(c in sig.columns for c in ["open", "high", "low", "close"]):
        df_engine = sig[["open", "high", "low", "close"]].copy()
    else:
        # Fallback to original df (supporting the provider’s column names)
        df_engine = df.rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"}
        )
        missing = [c for c in ["open", "high", "low", "close"] if c not in df_engine]
        if missing:
            raise ValueError(f"OHLC columns missing for engine: {missing}")

    # Convert persistent states to one-bar events
    entry_state = sig.get("long_entry", pd.Series(False, index=df_engine.index)).astype(
        bool
    )
    exit_state = sig.get("long_exit", pd.Series(False, index=df_engine.index)).astype(
        bool
    )

    entry_event = entry_state & ~entry_state.shift(1, fill_value=False)
    exit_event = exit_state & ~exit_state.shift(1, fill_value=False)

    # If engine executes next-bar by design and we are NOT entering on break bar,
    # shift the edge events to the following bar.
    if not getattr(p, "enter_on_break_bar", False):
        entry_event = entry_event.shift(1, fill_value=False)
        exit_event = exit_event.shift(1, fill_value=False)

    # Sanity: keep indexes aligned and dtype boolean
    if not entry_event.index.equals(df_engine.index) or not exit_event.index.equals(
        df_engine.index
    ):
        entry_event = entry_event.reindex(df_engine.index, fill_value=False)
        exit_event = exit_event.reindex(df_engine.index, fill_value=False)
    entry_event = entry_event.astype(bool)
    exit_event = exit_event.astype(bool)

    # Diagnostics
    if debug:
        log.debug(
            "Signals: entries=%d exits=%d rows=%d",
            int(sig.get("long_entry", pd.Series()).sum()) if "long_entry" in sig else 0,
            int(sig.get("long_exit", pd.Series()).sum()) if "long_exit" in sig else 0,
            len(sig),
        )
        log.debug(
            "Events: entry_event=%d exit_event=%d",
            int(entry_event.sum()),
            int(exit_event.sum()),
        )

    # Optional signal dumps
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
            mask = sig.get("long_entry", False) | sig.get("long_exit", False)
            sig.loc[mask, cols_dbg_all].tail(200).to_csv(
                f"signals_events_{symbol}.csv"
            )
            log.debug(
                "Saved signal snapshots: signals_tail_%s.csv, signals_events_%s.csv",
                symbol,
                symbol,
            )
        except Exception as e_dump:
            log.debug("Signal dump failed: %s", e_dump)

    beta = BetaWinrate()
    default_risk = (
        0.01 * beta.kelly_fraction() / max(beta.fmax, 1e-6) if beta.fmax > 0 else 0.01
    )

    atr_series = sig.get("atr")
    if atr_series is None:
        raise ValueError("Signal frame must contain 'atr' column")

    bt_kwargs: Dict[str, Any] = dict(
        df=df_engine,
        entry=entry_event,  # pass one-bar boolean events (Series for engine .iloc)
        exit_=exit_event,  # pass one-bar boolean events
        atr=atr_series,
        entry_price=p.entry_price,
        atr_mult=p.atr_mult,
        risk_frac=(risk_frac_override if risk_frac_override is not None else default_risk),
        costs=Costs(
            slippage_bps=slippage_bps if slippage_bps is not None else 1.0,
            fee_per_share=fee_per_share if fee_per_share is not None else 0.0,
        ),
        model=beta,
        min_notional=min_notional,
    )

    res, used_extra = _try_backtest(backtest_long_only, bt_kwargs)
    if used_extra:
        log.debug("backtest_long_only extra kwargs applied: %s", used_extra)

    # Introspection
    try:
        trades_obj = res.get("trades")
        trades_len = len(trades_obj) if hasattr(trades_obj, "__len__") else -1
        log.debug("trades_len=%s", trades_len)
        if trades_len > 0:
            preview = trades_obj[: min(3, trades_len)]
            log.debug("first_trades=%s", preview)
    except Exception as e_tr:
        log.debug("Trades introspection failed: %s", e_tr)

    try:
        keys = list(res.keys())
        log.debug("result keys: %s", keys)
        eq = res.get("equity")
        if eq is not None and hasattr(eq, "diff"):
            moved = float(np.nansum(np.abs(eq.diff().to_numpy()))) if hasattr(eq, "to_numpy") else float(
                np.nansum(np.abs(eq.diff().values))
            )
            log.debug("equity moved (abs sum diffs): %.6f", moved)
    except Exception as e_keys:
        log.debug("Result introspection failed: %s", e_keys)

    # Equity flatline diagnostics
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
                log.debug("Equity move calc failed: %s", e_calc)
                flat = False
        if flat or debug_signals:
            invalid_atr = None
            if {"long_entry", "atr_ok"}.issubset(sig.columns):
                invalid_atr = int((sig["long_entry"] & (~sig["atr_ok"])).sum())
                log.debug("entries with invalid ATR: %s", invalid_atr)
            elif {"long_entry", "atr"}.issubset(sig.columns):
                invalid_atr = int((sig["long_entry"] & (~sig["atr"].gt(0))).sum())
                log.debug("entries with invalid ATR(alt): %s", invalid_atr)

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
            log.debug("Equity flat; saved snapshot -> %s", dbg2_path)
    except Exception as e_diag:
        log.debug("Equity-flat diagnostics failed: %s", e_diag)

    # Metrics & outputs
    m = bt_metrics.equity_stats(res["equity"], use_mtm=True)
    m_dict = asdict(m)
    m_pretty = {k: _roundish(v) for k, v in m_dict.items()}
    log.info("[%s] equity metrics: %s", symbol, m_pretty)
    out_dir = os.getenv("BACKTEST_OUT_DIR", ".")
    out_name = f"backtest_{symbol}.csv"
    out = os.path.join(out_dir, out_name)
    if os.getenv("BACKTEST_NO_SAVE", "0") == "1":
        log.info("Skipping save of equity curve due to BACKTEST_NO_SAVE=1")
    else:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        res["equity"].to_csv(out)
        log.info("Saved equity curve -> %s", out)


if __name__ == "__main__":
    # Minimal logging config for CLI use; app runtime can configure root logging.
    _setup_cli_logging(logging.INFO)

    ap = argparse.ArgumentParser(
        description="Run breakout backtest with configurable parameters"
    )
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", default=None)
    ap.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to write outputs (default: BACKTEST_OUT_DIR env or current dir)",
    )
    ap.add_argument(
        "--no-save",
        dest="no_save",
        action="store_true",
        default=False,
        help="Do not write the equity CSV to disk",
    )
    ap.add_argument(
        "--print-metrics-json",
        dest="print_metrics_json",
        action="store_true",
        default=False,
        help="Print metrics as a single JSON line to stdout (useful in CI)",
    )

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
    if args.out_dir:
        os.environ["BACKTEST_OUT_DIR"] = args.out_dir
    if args.no_save:
        os.environ["BACKTEST_NO_SAVE"] = "1"

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

    try:
        run(
            args.symbol,
            args.start,
            args.end,
            params_kwargs=params_kwargs,
            slippage_bps=args.slippage_bps,
            fee_per_share=args.fee_per_share,
            risk_frac_override=args.risk_frac,
            min_notional=args.min_notional,
            debug=args.debug,
            debug_signals=args.debug_signals or args.debug,
            debug_entries=args.debug_entries or args.debug,
        )
        if args.print_metrics_json:
            # Determine output file and emit metrics as JSON if available
            out_dir = os.getenv("BACKTEST_OUT_DIR", ".")
            out = os.path.join(out_dir, f"backtest_{args.symbol}.csv")
            if os.path.exists(out):
                eq = pd.read_csv(out, index_col=0, parse_dates=True).iloc[:, 0]
                m = bt_metrics.equity_stats(eq, use_mtm=True)
                print(json.dumps({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in asdict(m).items()}))
    except Exception as e:
        log.error("Backtest run failed: %s", e)
        log.debug("Traceback:\n%s", traceback.format_exc())
        sys.exit(1)
