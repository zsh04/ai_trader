from __future__ import annotations

from dataclasses import dataclass, is_dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BreakoutParams:
    lookback: int = 20  # breakout window
    ema_fast: int = 20  # trend filter
    atr_len: int = 14  # ATR for stop/sizing
    atr_mult: float = 2.0  # initial stop distance
    hold_bars: int = 10  # optional time exit; 0 = disabled
    entry_price: str = "close"  # "close" or "next_open"
    exit_on_ema_break: bool = True
    use_ema_filter: bool = True  # require close > EMA for entries
    breakout_buffer_pct: float = 0.0  # e.g., 0.001 = +0.1% above hh
    min_break_valid: int | None = None  # override min_periods for hh; None => n_break
    confirm_with_high: bool = True  # if True, use high >= HH; else use close >= HH
    use_close_for_breakout: bool = False  # use rolling max of CLOSE instead of HIGH
    enter_on_break_bar: bool = False  # enter on same bar (no shift) instead of next bar


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_c = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_c).abs(), (low - prev_c).abs()))
    return tr.rolling(n, min_periods=n).mean()


def _get(p: Any, key: str, default: Any) -> Any:
    """Read param from dict or dataclass; fallback to default."""
    if isinstance(p, Mapping):
        return p.get(key, default)
    if is_dataclass(p):
        return getattr(p, key, default)
    # last resort: try attribute, then default
    return getattr(p, key, default)


def _as_series(obj: Any) -> pd.Series:
    """Coerce single-column DataFrames to Series; pass Series through."""
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0]
    return obj


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """
    Return a Series for the given column name, even if the frame contains
    duplicate column names (which would otherwise return a 2D frame).
    """
    obj = df.loc[:, name]
    if isinstance(obj, pd.DataFrame):
        obj = obj.iloc[:, 0]
    return obj


# Flexible column resolver for OHLC columns with fuzzy matching
def _pick_col(df: pd.DataFrame, *candidates: str) -> pd.Series:
    """
    Return a Series for the first matching candidate column name.
    Tries exact match on normalized, lowercased columns first, then
    a few common fuzzy patterns (prefix/suffix/substring).
    Raises a clear KeyError if nothing matches.
    """
    cols = list(df.columns)
    # 1) exact match
    for name in candidates:
        if name in df.columns:
            return _col(df, name)

    # 2) common fuzzy matches
    def _match(name: str) -> str | None:
        for c in cols:
            if c == name:
                return c
            if c.startswith(name + "_") or c.endswith("_" + name):
                return c
            if name in c:
                return c
        return None

    for name in candidates:
        hit = _match(name)
        if hit is not None:
            return _col(df, hit)
    raise KeyError(
        f"None of the columns {candidates} found in DataFrame. Available: {cols[:12]}{'...' if len(cols) > 12 else ''}"
    )


def generate_signals(df: pd.DataFrame, p: Any) -> pd.DataFrame:
    """
    Expects df with columns: open, high, low, close, volume
    p may be a dict or a BreakoutParams dataclass.
    Returns the original OHLCV plus: hh, ema, atr, trail_stop, long_entry, long_exit
    """
    # Work on a clean, index-aligned copy
    out = df.copy().sort_index()

    # Normalize column names and de-duplicate to avoid DataFrame selections on dupes
    # Ultra-defensive: never call astype on a MultiIndex; always flatten via pure Python.
    try:
        cols = out.columns
        if isinstance(cols, pd.MultiIndex):
            # Flatten tuples like ('OHLC','close') -> 'OHLC_close'; drop Nones/empties
            flat = []
            for tup in cols.to_list():
                # Some loaders use non-tuple entries in a MultiIndex; normalize to tuple
                if not isinstance(tup, (tuple, list)):
                    tup = (tup,)
                parts = []
                for x in tup:
                    sx = "" if x is None else str(x)
                    sx = sx.strip()
                    if sx:
                        parts.append(sx)
                flat.append("_".join(parts))
            out.columns = pd.Index([s.lower() for s in flat])
        else:
            out.columns = pd.Index([str(c).strip().lower() for c in cols])
    except Exception:
        # Absolute fallback: stringify everything conservatively
        out.columns = pd.Index([str(c).strip().lower() for c in out.columns])

    # Drop duplicate columns, keeping the first occurrence
    out = out.loc[:, ~out.columns.duplicated(keep="first")]

    # Flexible param resolution: support both legacy keys and dataclass fields
    n_break = int(_get(p, "breakout_lookback", _get(p, "lookback", 20)))
    n_ema = int(_get(p, "ema", _get(p, "ema_fast", 50)))
    n_atr = int(_get(p, "atr", _get(p, "atr_len", 14)))
    atr_k = float(_get(p, "atr_mult", 2.0))

    use_ema = bool(_get(p, "use_ema_filter", True))
    buffer = float(_get(p, "breakout_buffer_pct", 0.0))
    minp = _get(p, "min_break_valid", None)
    minp = int(minp) if minp is not None else n_break
    confirm_with_high = bool(_get(p, "confirm_with_high", True))
    use_close_brk = bool(_get(p, "use_close_for_breakout", False))
    enter_samebar = bool(_get(p, "enter_on_break_bar", False))

    # Safe Series accessors (handle duplicates and flexible names deterministically)
    high = _pick_col(out, "high", "ohlc_high", "h")
    low = _pick_col(out, "low", "ohlc_low", "l")
    close = _pick_col(out, "close", "adj_close", "close_price", "c", "ohlc_close")

    # Highest high of prior N bars (no look-ahead or same-bar logic)
    brk_base = close if use_close_brk else high
    hh_raw = brk_base.rolling(n_break, min_periods=minp).max()
    if not enter_samebar:
        hh_raw = hh_raw.shift(1)  # classic: use prior-bar HH to avoid lookahead
    ema_raw = close.ewm(span=n_ema, adjust=False).mean()

    # True Range and ATR
    prev_c = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_c).abs(),
            (low - prev_c).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_raw = tr.rolling(n_atr, min_periods=n_atr).mean()

    # Defensive normalization and alignment (ensure Series and identical index)
    hh = _as_series(hh_raw).reindex(out.index)
    ema = _as_series(ema_raw).reindex(out.index)
    atr_raw = _as_series(atr_raw).reindex(out.index)

    # --- ATR hardening: never allow NaN/Inf/<=0 to leak into sizing ---
    atr_safe = atr_raw.replace([np.inf, -np.inf], np.nan)
    # Try to fill from nearby context to preserve structure
    atr_safe = atr_safe.bfill().ffill()
    # If still bad, use rolling mean as a softer fallback
    atr_safe = atr_safe.where(atr_safe > 0, atr_safe.rolling(5, min_periods=1).mean())
    # Final clamp
    atr_safe = atr_safe.fillna(
        float(atr_safe.median()) if not np.isnan(atr_safe.median()) else 1e-6
    )
    atr_safe = atr_safe.clip(lower=1e-6)

    # Basic validity flag for ATR at potential entry bars
    atr = atr_safe
    atr_ok = atr.gt(0) & np.isfinite(atr)

    # Signals (pure Series math)
    hh_buf = hh * (1.0 + buffer)
    trend_ok = (close > ema) if use_ema else pd.Series(True, index=out.index)
    trigger = (high >= hh_buf) if confirm_with_high else (close >= hh_buf)
    long_entry = trigger & trend_ok & hh.notna()

    trail_stop = close - atr_k * atr

    # Respect EMA exit only if exit_on_ema_break is enabled (fallback True for legacy)
    exit_on_ema = bool(_get(p, "exit_on_ema_break", True))
    ema_exit = (
        (close < ema)
        if (exit_on_ema and use_ema)
        else pd.Series(False, index=out.index)
    )
    long_exit = ema_exit | (low < trail_stop.shift(1))

    # Persist diagnostics
    out["hh"] = hh
    out["ema"] = ema
    out["atr"] = atr
    out["trail_stop"] = trail_stop

    # Booleans with NaNs guarded
    out["long_entry"] = long_entry.fillna(False)
    out["long_exit"] = long_exit.fillna(False)

    # --- Diagnostics (helpful when entries == 0) ---
    out["hh_buf"] = hh_buf
    out["trend_ok"] = trend_ok.fillna(False)
    out["trigger"] = trigger.fillna(False)
    out["atr_ok"] = atr_ok.fillna(False)

    return out
