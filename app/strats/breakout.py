from __future__ import annotations

from dataclasses import dataclass, is_dataclass
from typing import Any, Mapping
import re
import numpy as np
import pandas as pd


# --- Params -----------------------------------------------------------------

@dataclass(frozen=True)
class BreakoutParams:
    lookback: int = 20              # breakout window
    ema_fast: int = 20              # trend filter
    atr_len: int = 14               # ATR for stop/sizing
    atr_mult: float = 2.0           # initial stop distance (trail = close - k*ATR)
    hold_bars: int = 10             # optional time exit; 0 = disabled (reserved)
    entry_price: str = "close"      # "close" or "next_open" (reserved)
    exit_on_ema_break: bool = True  # exit when close < EMA (if EMA filter enabled)
    use_ema_filter: bool = True     # require close > EMA for entries
    breakout_buffer_pct: float = 0.0  # e.g. 0.001 => +0.1% above hh
    min_break_valid: int | None = None  # override min_periods for hh
    confirm_with_high: bool = True     # use high >= HH; else close >= HH
    use_close_for_breakout: bool = False  # rolling max of CLOSE instead of HIGH
    enter_on_break_bar: bool = False      # enter on same bar (no shift) vs next bar


# --- Small utils -------------------------------------------------------------

def _get(p: Any, key: str, default: Any) -> Any:
    """Read param from dict or dataclass; fallback to default."""
    if isinstance(p, Mapping):
        return p.get(key, default)
    if is_dataclass(p):
        return getattr(p, key, default)
    return getattr(p, key, default)


def _as_series(obj: pd.Series | pd.DataFrame) -> pd.Series:
    """Coerce single-column DataFrames to Series."""
    return obj.iloc[:, 0] if isinstance(obj, pd.DataFrame) else obj


def _first_column(df: pd.DataFrame, name: str) -> pd.Series:
    """Select first column when duplicates exist."""
    sel = df.loc[:, name]
    return sel.iloc[:, 0] if isinstance(sel, pd.DataFrame) else sel


def _pick_col(df: pd.DataFrame, *candidates: str) -> pd.Series:
    """
    Return Series for first matching candidate.
    Exact match first; then fallback to simple fuzzy (prefix/suffix/substring).
    """
    cols = list(df.columns)

    # exact
    for name in candidates:
        if name in df.columns:
            return _first_column(df, name)

    # fuzzy
    def _match(name: str) -> str | None:
        for c in cols:
            if c == name or c.startswith(name + "_") or c.endswith("_" + name) or (name in c):
                return c
        return None

    for name in candidates:
        hit = _match(name)
        if hit is not None:
            return _first_column(df, hit)

    raise KeyError(f"None of {candidates} found. Available: {cols[:12]}{'...' if len(cols) > 12 else ''}")


# --- Core --------------------------------------------------------------------

def generate_signals(df: pd.DataFrame, p: Any) -> pd.DataFrame:
    """
    Input: DataFrame with columns like open/high/low/close/volume (case-insensitive).
    Output: same index + columns:
        hh, ema, atr, trail_stop, long_entry, long_exit, hh_buf, trend_ok, trigger, atr_ok
    """
    out = df.copy().sort_index()

    # Normalize columns; flatten MultiIndex defensively
    try:
        cols = out.columns
        if isinstance(cols, pd.MultiIndex):
            flat = []
            for tup in cols.to_list():
                if not isinstance(tup, (tuple, list)):
                    tup = (tup,)
                parts = [str(x).strip() for x in tup if str(x).strip()]
                flat.append("_".join(parts))
            out.columns = pd.Index([s.lower() for s in flat])
        else:
            out.columns = pd.Index([str(c).strip().lower() for c in cols])
    except Exception:
        out.columns = pd.Index([str(c).strip().lower() for c in out.columns])

    # Drop duplicate column names, keep first
    out = out.loc[:, ~out.columns.duplicated(keep="first")]

    # Resolve params (support legacy keys)
    n_break = int(_get(p, "breakout_lookback", _get(p, "lookback", 20)))
    n_ema   = int(_get(p, "ema", _get(p, "ema_fast", 20)))
    n_atr   = int(_get(p, "atr", _get(p, "atr_len", 14)))
    atr_k   = float(_get(p, "atr_mult", 2.0))

    use_ema = bool(_get(p, "use_ema_filter", True))
    buffer  = float(_get(p, "breakout_buffer_pct", 0.0))
    minp    = int(_get(p, "min_break_valid", n_break) or n_break)
    confirm_with_high = bool(_get(p, "confirm_with_high", True))
    use_close_brk     = bool(_get(p, "use_close_for_breakout", False))
    enter_samebar     = bool(_get(p, "enter_on_break_bar", False))
    exit_on_ema       = bool(_get(p, "exit_on_ema_break", True))

    # OHLC (robust name resolution)
    high  = _pick_col(out, "high", "ohlc_high", "h")
    low   = _pick_col(out, "low", "ohlc_low", "l")
    close = _pick_col(out, "close", "adj_close", "close_price", "c", "ohlc_close")

    # Highest high of prior N bars (no look-ahead unless enter_on_break_bar=True)
    brk_base = close if use_close_brk else high
    hh = brk_base.rolling(n_break, min_periods=minp).max()
    if not enter_samebar:
        hh = hh.shift(1)

    ema = close.ewm(span=n_ema, adjust=False).mean()

    # ATR (simple rolling mean of True Range; safe & positive)
    prev_c = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n_atr, min_periods=n_atr).mean()
    atr = _as_series(atr).replace([np.inf, -np.inf], np.nan).bfill().ffill()
    atr = atr.where(atr > 0, atr.rolling(5, min_periods=1).mean()).fillna(atr.median() if pd.notna(atr.median()) else 1e-6)
    atr = atr.clip(lower=1e-6)

    # Signals
    hh_buf   = hh * (1.0 + buffer)
    trend_ok = (close > ema) if use_ema else pd.Series(True, index=out.index)
    trigger  = (high >= hh_buf) if confirm_with_high else (close >= hh_buf)
    long_entry = (trigger & trend_ok & hh.notna()).fillna(False)

    trail_stop = (close - atr_k * atr)
    ema_exit   = (close < ema) if (exit_on_ema and use_ema) else pd.Series(False, index=out.index)
    long_exit  = (ema_exit | (low < trail_stop.shift(1))).fillna(False)

    # Persist
    out["hh"]          = _as_series(hh).reindex(out.index)
    out["ema"]         = _as_series(ema).reindex(out.index)
    out["atr"]         = atr.reindex(out.index)
    out["trail_stop"]  = _as_series(trail_stop).reindex(out.index)
    out["long_entry"]  = long_entry
    out["long_exit"]   = long_exit

    # Diagnostics
    out["hh_buf"]   = _as_series(hh_buf).reindex(out.index)
    out["trend_ok"] = trend_ok.fillna(False)
    out["trigger"]  = trigger.fillna(False)
    out["atr_ok"]   = atr.gt(0) & np.isfinite(atr)

    return out