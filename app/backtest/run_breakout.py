from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from pandas import Timestamp

from app.backtest import metrics as bt_metrics
from app.backtest.engine import Costs, backtest_long_only
from app.backtest.model import BetaWinrate
from app.logging_utils import setup_logging
from app.dal.manager import MarketDataDAL as _LegacyMarketDataDAL
from app.probability.pipeline import (
    ProbabilisticConfig,
    fetch_probabilistic_batch,
    join_probabilistic_features,
)
from app.providers.yahoo_provider import get_history_daily
from app.strats.breakout import BreakoutParams, generate_signals

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------


def _setup_cli_logging(level: str = "INFO") -> None:
    """
    Idempotent CLI logging initializer. Keeps uvicorn/fastapi logs quiet when used as a script,
    and provides consistent formatting for CI logs.
    """
    setup_logging(force=True, level=level)


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

# Backwards compatibility for tests/monkeypatch
MarketDataDAL = _LegacyMarketDataDAL


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
    regime_aware_sizing: bool = False,
    use_probabilistic: bool = False,
    dal_vendor: str = "alpaca",
    dal_interval: str = "1Day",
    export_csv: str | None = None,
) -> None:
    """
    Execute a long-only breakout backtest for a single symbol.
    """
    start_dt = pd.to_datetime(start).date()
    end_dt = pd.to_datetime(end).date() if end else datetime.now(UTC).date()

    logger.info("Fetching daily history for {}: {} → {}", symbol, start_dt, end_dt)
    df = get_history_daily(symbol, start_dt, end_dt).dropna().copy()
    if df.empty:
        logger.error(
            "No history returned for {} in [{}, {}]. Check data provider/API keys.",
            symbol,
            start_dt,
            end_dt,
        )
        return

    start_ts = datetime.combine(start_dt, datetime.min.time(), tzinfo=UTC)
    end_ts = (
        datetime.combine(end_dt, datetime.min.time(), tzinfo=UTC) + timedelta(days=1)
        if end
        else None
    )

    # Strategy params
    p = BreakoutParams(**params_kwargs)
    sig = generate_signals(df, asdict(p))

    prob_batch = None
    if use_probabilistic:
        try:
            dal_instance = MarketDataDAL(enable_postgres_metadata=False)
            prob_batch = fetch_probabilistic_batch(
                symbol,
                start=start_ts,
                end=end_ts,
                config=ProbabilisticConfig(
                    vendor=dal_vendor,
                    interval=dal_interval,
                    enable_metadata_persist=False,
                ),
                dal=dal_instance,
            )
            logger.info(
                "Probabilistic DAL fetch ok vendor={} interval={} bars={} signals={} regimes={}",
                dal_vendor,
                dal_interval,
                len(prob_batch.bars.data),
                len(prob_batch.signals),
                len(prob_batch.regimes),
            )
            if prob_batch.cache_paths:
                logger.debug("Probabilistic cache artifacts: {}", prob_batch.cache_paths)

            sig = join_probabilistic_features(
                sig, signals=prob_batch.signals, regimes=prob_batch.regimes
            )
            joined_cols = [
                col
                for col in ("prob_filtered_price", "regime_label")
                if col in sig.columns
            ]
            if joined_cols:
                nonnull = sig[joined_cols].count()
                logger.debug(
                    "Probabilistic features joined: {}",
                    {col: int(nonnull.get(col, 0)) for col in joined_cols},
                )
        except Exception as err:
            logger.warning(
                "Probabilistic DAL fetch failed (vendor={}, interval={}): {}",
                dal_vendor,
                dal_interval,
                err,
            )
            prob_batch = None
    elif regime_aware_sizing:
        logger.warning(
            "Regime-aware sizing requested but --use-probabilistic disabled; ignoring regime sizing toggle."
        )

    # Engine OHLC input (ensure lowercase columns)
    if all(c in sig.columns for c in ["open", "high", "low", "close"]):
        df_engine = sig[["open", "high", "low", "close"]].copy()
    else:
        # Fallback to original df (supporting the provider’s column names)
        df_engine = df.rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"}
        )
        missing = [
            c for c in ["open", "high", "low", "close"] if c not in df_engine
        ]
        if missing:
            raise ValueError(f"OHLC columns missing for engine: {missing}")

    # Convert persistent states to one-bar events
    entry_state = sig.get(
        "long_entry", pd.Series(False, index=df_engine.index)
    ).astype(bool)
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
        logger.debug(
            "Signals: entries={} exits={} rows={}",
            int(sig.get("long_entry", pd.Series()).sum())
            if "long_entry" in sig
            else 0,
            int(sig.get("long_exit", pd.Series()).sum()) if "long_exit" in sig else 0,
            len(sig),
        )
        logger.debug(
            "Events: entry_event={} exit_event={}",
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
                "prob_filtered_price",
                "prob_velocity",
                "prob_uncertainty",
                "prob_butterworth_price",
                "prob_ema_price",
                "regime_label",
                "regime_volatility",
                "regime_uncertainty",
                "regime_momentum",
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
            logger.debug(
                "Saved signal snapshots: signals_tail_{}.csv, signals_events_{}.csv",
                symbol,
                symbol,
            )
        except Exception as e_dump:
            logger.debug("Signal dump failed: {}", e_dump)

    beta = BetaWinrate()
    default_risk = (
        0.01 * beta.kelly_fraction() / max(beta.fmax, 1e-6)
        if beta.fmax > 0
        else 0.01
    )

    base_risk_frac = (
        risk_frac_override if risk_frac_override is not None else default_risk
    )
    risk_multiplier = 1.0
    applied_regime = None
    applied_uncertainty = None
    if regime_aware_sizing and prob_batch:
        regime_series = sig.get("regime_label")
        if regime_series is not None:
            regime_values = regime_series.dropna()
            if not regime_values.empty:
                applied_regime = str(regime_values.iloc[-1])
                regime_scalers = {
                    "trend_up": 1.0,
                    "trend_down": 0.6,
                    "high_volatility": 0.5,
                    "uncertain": 0.4,
                    "sideways": 0.7,
                    "calm": 0.85,
                }
                risk_multiplier = regime_scalers.get(applied_regime, 1.0)
                uncertainty_series = sig.get("regime_uncertainty")
                if uncertainty_series is not None:
                    uncertainty_values = uncertainty_series.dropna()
                    if not uncertainty_values.empty:
                        applied_uncertainty = float(uncertainty_values.iloc[-1])
                        if applied_uncertainty > 0.05:
                            risk_multiplier *= 0.7
                risk_multiplier = max(min(risk_multiplier, 1.0), 0.1)
                logger.info(
                    "Regime-aware sizing applied: regime={} uncertainty={} scale={:.3f}",
                    applied_regime,
                    (
                        f"{applied_uncertainty:.4f}"
                        if applied_uncertainty is not None
                        else "n/a"
                    ),
                    risk_multiplier,
                )
            else:
                logger.warning(
                    "Regime-aware sizing enabled but regime series contained only NaNs."
                )
        else:
            logger.warning(
                "Regime-aware sizing enabled but regime_label column not found."
            )

    risk_frac_value = base_risk_frac * risk_multiplier

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
        risk_frac=risk_frac_value,
        costs=Costs(
            slippage_bps=slippage_bps if slippage_bps is not None else 1.0,
            fee_per_share=fee_per_share if fee_per_share is not None else 0.0,
        ),
        model=beta,
        min_notional=min_notional,
    )

    res, used_extra = _try_backtest(backtest_long_only, bt_kwargs)
    if used_extra:
        logger.debug("backtest_long_only extra kwargs applied: {}", used_extra)

    # Introspection
    try:
        trades_obj = res.get("trades")
        trades_len = len(trades_obj) if hasattr(trades_obj, "__len__") else -1
        logger.debug("trades_len={}", trades_len)
        if trades_len > 0:
            preview = trades_obj[: min(3, trades_len)]
            logger.debug("first_trades={}", preview)
    except Exception as e_tr:
        logger.debug("Trades introspection failed: {}", e_tr)

    try:
        keys = list(res.keys())
        logger.debug("result keys: {}", keys)
        eq = res.get("equity")
        if eq is not None and hasattr(eq, "diff"):
            moved = (
                float(np.nansum(np.abs(eq.diff().to_numpy())))
                if hasattr(eq, "to_numpy")
                else float(np.nansum(np.abs(eq.diff().values)))
            )
            logger.debug("equity moved (abs sum diffs): {:.6f}", moved)
    except Exception as e_keys:
        logger.debug("Result introspection failed: {}", e_keys)

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
                logger.debug("Equity move calc failed: {}", e_calc)
                flat = False
        if flat or debug_signals:
            invalid_atr = None
            if {"long_entry", "atr_ok"}.issubset(sig.columns):
                invalid_atr = int((sig["long_entry"] & (~sig["atr_ok"])).sum())
                logger.debug("entries with invalid ATR: {}", invalid_atr)
            elif {"long_entry", "atr"}.issubset(sig.columns):
                invalid_atr = int((sig["long_entry"] & (~sig["atr"].gt(0))).sum())
                logger.debug("entries with invalid ATR(alt): {}", invalid_atr)

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
                    "prob_filtered_price",
                    "prob_velocity",
                    "prob_uncertainty",
                    "prob_butterworth_price",
                    "prob_ema_price",
                    "regime_label",
                    "regime_volatility",
                    "regime_uncertainty",
                    "regime_momentum",
                    "long_entry",
                    "long_exit",
                ]
                if c in sig.columns
            ]
            snap = sig[cols_dbg2].tail(100) if cols_dbg2 else sig.tail(100)
            dbg2_path = f"signals_flat_debug_{symbol}.csv"
            snap.to_csv(dbg2_path)
            logger.debug("Equity flat; saved snapshot -> {}", dbg2_path)
    except Exception as e_diag:
        logger.debug("Equity-flat diagnostics failed: {}", e_diag)

    # Metrics & outputs
    m = bt_metrics.equity_stats(res["equity"], use_mtm=True)
    m_dict = asdict(m)
    m_pretty = {k: _roundish(v) for k, v in m_dict.items()}
    logger.info("[{}] equity metrics: {}", symbol, m_pretty)
    out_dir = os.getenv("BACKTEST_OUT_DIR", ".")
    out_name = f"backtest_{symbol}.csv"
    out = os.path.join(out_dir, out_name)
    if os.getenv("BACKTEST_NO_SAVE", "0") == "1":
        logger.info("Skipping save of equity curve due to BACKTEST_NO_SAVE=1")
    else:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        res["equity"].to_csv(out)
        logger.info("Saved equity curve -> {}", out)

    if export_csv:
        export_dir = Path(export_csv).expanduser()
        export_dir.mkdir(parents=True, exist_ok=True)

        equity_data = res.get("equity")
        if isinstance(equity_data, pd.DataFrame):
            eq_df = equity_data.copy()
        elif isinstance(equity_data, pd.Series):
            eq_df = equity_data.to_frame(name="equity")
        else:
            eq_df = pd.DataFrame()

        equity_path = (export_dir / f"{symbol}_equity.csv").resolve()
        eq_df.to_csv(equity_path)
        logger.info("Exported equity CSV -> {}", equity_path)

        trades = res.get("trades")
        if isinstance(trades, pd.DataFrame):
            trades_df = trades.copy()
        elif isinstance(trades, (list, tuple)):
            trades_df = pd.DataFrame(trades)
        else:
            trades_df = pd.DataFrame()

        trades_path = (export_dir / f"{symbol}_trades.csv").resolve()
        trades_df.to_csv(trades_path, index=False)
        logger.info("Exported trades CSV -> {}", trades_path)


if __name__ == "__main__":
    # Minimal logging config for CLI use; app runtime can configure root logging.
    _setup_cli_logging("INFO")

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
    ap.add_argument(
        "--export-csv",
        dest="export_csv",
        default=None,
        help="Directory to write <symbol>_equity.csv and <symbol>_trades.csv exports",
    )
    ap.add_argument(
        "--use-probabilistic",
        dest="use_probabilistic",
        action="store_true",
        default=False,
        help="Fetch bars via MarketDataDAL and join probabilistic signals/regimes into the breakout frame.",
    )
    ap.add_argument(
        "--dal-vendor",
        dest="dal_vendor",
        default="alpaca",
        help="MarketDataDAL vendor key when --use-probabilistic is enabled (default: alpaca).",
    )
    ap.add_argument(
        "--dal-interval",
        dest="dal_interval",
        default="1Day",
        help="MarketDataDAL bar interval when --use-probabilistic is enabled (default: 1Day).",
    )
    ap.add_argument(
        "--regime-aware-sizing",
        dest="regime_aware_sizing",
        action="store_true",
        default=False,
        help="Scale breakout risk fraction using the latest probabilistic regime snapshot (requires --use-probabilistic).",
    )

    # --- Strategy Parameters ---
    ap.add_argument(
        "--lookback", type=int, help="Breakout lookback window length"
    )
    ap.add_argument(
        "--ema", dest="ema_fast", type=int, help="EMA length for trend filter"
    )
    ap.add_argument(
        "--atr", dest="atr_len", type=int, help="ATR lookback period"
    )
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
        "--fee-per-share",
        dest="fee_per_share",
        type=float,
        help="Fee per share traded",
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
        k: getattr(args, k)
        for k in candidate_keys
        if getattr(args, k) is not None
    }
    # Filter out any keys not supported by BreakoutParams (handles version drift)
    try:
        allowed_keys = set(
            getattr(BreakoutParams, "__annotations__", {}).keys()
        )
    except Exception:
        allowed_keys = set()
    params_kwargs = {
        k: v for k, v in raw_kwargs.items() if k in allowed_keys
    }

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
            regime_aware_sizing=args.regime_aware_sizing,
            use_probabilistic=args.use_probabilistic,
            dal_vendor=args.dal_vendor,
            dal_interval=args.dal_interval,
            export_csv=args.export_csv,
        )
        if args.print_metrics_json:
            # Determine output file and emit metrics as JSON if available
            out_dir = os.getenv("BACKTEST_OUT_DIR", ".")
            out = os.path.join(out_dir, f"backtest_{args.symbol}.csv")
            if os.path.exists(out):
                eq = pd.read_csv(out, index_col=0, parse_dates=True).iloc[
                    :, 0
                ]
                m = bt_metrics.equity_stats(eq, use_mtm=True)
                print(
                    json.dumps(
                        {
                            k: (
                                v.isoformat()
                                if hasattr(v, "isoformat")
                                else v
                            )
                            for k, v in asdict(m).items()
                        }
                    )
                )
    except Exception as e:
        logger.error("Backtest run failed: {}", e)
        logger.debug("Traceback:\n{}", traceback.format_exc())
        sys.exit(1)
