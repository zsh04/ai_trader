from __future__ import annotations

from dataclasses import dataclass, is_dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BreakoutParams:
    """
    A data class for breakout strategy parameters.

    Attributes:
        lookback (int): The breakout window.
        ema_fast (int): The fast EMA period for the trend filter.
        atr_len (int): The ATR period for stop loss and sizing.
        atr_mult (float): The ATR multiplier for the initial stop distance.
        hold_bars (int): The number of bars to hold a position.
        entry_price (str): The entry price type.
        exit_on_ema_break (bool): Whether to exit on EMA break.
        use_ema_filter (bool): Whether to use an EMA filter for entries.
        breakout_buffer_pct (float): The breakout buffer percentage.
        min_break_valid (int | None): The minimum number of periods for a valid breakout.
        confirm_with_high (bool): Whether to confirm the breakout with the high price.
        use_close_for_breakout (bool): Whether to use the close price for breakouts.
        enter_on_break_bar (bool): Whether to enter on the same bar as the breakout.
    """
    lookback: int = 20
    ema_fast: int = 20
    atr_len: int = 14
    atr_mult: float = 2.0
    hold_bars: int = 10
    entry_price: str = "close"
    exit_on_ema_break: bool = True
    use_ema_filter: bool = True
    breakout_buffer_pct: float = 0.0
    min_break_valid: int | None = None
    confirm_with_high: bool = True
    use_close_for_breakout: bool = False
    enter_on_break_bar: bool = False


def _get(p: Any, key: str, default: Any) -> Any:
    """
    Gets a parameter from a dictionary or dataclass.

    Args:
        p (Any): The dictionary or dataclass.
        key (str): The key to get.
        default (Any): The default value to return if the key is not found.

    Returns:
        Any: The value of the parameter.
    """
    if isinstance(p, Mapping):
        return p.get(key, default)
    if is_dataclass(p):
        return getattr(p, key, default)
    return getattr(p, key, default)


def _as_series(obj: pd.Series | pd.DataFrame) -> pd.Series:
    """
    Converts a single-column DataFrame to a Series.

    Args:
        obj (pd.Series | pd.DataFrame): The object to convert.

    Returns:
        pd.Series: The converted Series.
    """
    return obj.iloc[:, 0] if isinstance(obj, pd.DataFrame) else obj


def _first_column(df: pd.DataFrame, name: str) -> pd.Series:
    """
    Selects the first column with a given name.

    Args:
        df (pd.DataFrame): The DataFrame to select from.
        name (str): The name of the column to select.

    Returns:
        pd.Series: The selected column.
    """
    sel = df.loc[:, name]
    return sel.iloc[:, 0] if isinstance(sel, pd.DataFrame) else sel


def _pick_col(df: pd.DataFrame, *candidates: str) -> pd.Series:
    """
    Picks a column from a DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to pick from.
        *candidates (str): A list of candidate column names.

    Returns:
        pd.Series: The picked column.
    """
    cols = list(df.columns)

    for name in candidates:
        if name in df.columns:
            return _first_column(df, name)

    def _match(name: str) -> str | None:
        for c in cols:
            if (
                c == name
                or c.startswith(name + "_")
                or c.endswith("_" + name)
                or (name in c)
            ):
                return c
        return None

    for name in candidates:
        hit = _match(name)
        if hit is not None:
            return _first_column(df, hit)

    raise KeyError(
        f"None of {candidates} found. Available: {cols[:12]}{'...' if len(cols) > 12 else ''}"
    )


def generate_signals(df: pd.DataFrame, p: Any) -> pd.DataFrame:
    """
    Generates trading signals for a breakout strategy.

    Args:
        df (pd.DataFrame): A DataFrame with OHLCV data.
        p (Any): A dictionary or dataclass with the strategy parameters.

    Returns:
        pd.DataFrame: A DataFrame with the generated signals.
    """
    out = df.copy().sort_index()

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

    out = out.loc[:, ~out.columns.duplicated(keep="first")]

    n_break = int(_get(p, "breakout_lookback", _get(p, "lookback", 20)))
    n_ema = int(_get(p, "ema", _get(p, "ema_fast", 20)))
    n_atr = int(_get(p, "atr", _get(p, "atr_len", 14)))
    atr_k = float(_get(p, "atr_mult", 2.0))

    use_ema = bool(_get(p, "use_ema_filter", True))
    buffer = float(_get(p, "breakout_buffer_pct", 0.0))
    minp = int(_get(p, "min_break_valid", n_break) or n_break)
    confirm_with_high = bool(_get(p, "confirm_with_high", True))
    use_close_brk = bool(_get(p, "use_close_for_breakout", False))
    enter_samebar = bool(_get(p, "enter_on_break_bar", False))
    exit_on_ema = bool(_get(p, "exit_on_ema_break", True))

    high = _pick_col(out, "high", "ohlc_high", "h")
    low = _pick_col(out, "low", "ohlc_low", "l")
    close = _pick_col(out, "close", "adj_close", "close_price", "c", "ohlc_close")

    brk_base = close if use_close_brk else high
    hh = brk_base.rolling(n_break, min_periods=minp).max()
    if not enter_samebar:
        hh = hh.shift(1)

    ema = close.ewm(span=n_ema, adjust=False).mean()

    prev_c = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_c).abs(), (low - prev_c).abs()], axis=1
    ).max(axis=1)
    atr = tr.rolling(n_atr, min_periods=n_atr).mean()
    atr = _as_series(atr).replace([np.inf, -np.inf], np.nan).bfill().ffill()
    atr = atr.where(atr > 0, atr.rolling(5, min_periods=1).mean()).fillna(
        atr.median() if pd.notna(atr.median()) else 1e-6
    )
    atr = atr.clip(lower=1e-6)

    hh_buf = hh * (1.0 + buffer)
    trend_ok = (close > ema) if use_ema else pd.Series(True, index=out.index)
    trigger = (high >= hh_buf) if confirm_with_high else (close >= hh_buf)
    long_entry = (trigger & trend_ok & hh.notna()).fillna(False)

    trail_stop = close - atr_k * atr
    ema_exit = (
        (close < ema)
        if (exit_on_ema and use_ema)
        else pd.Series(False, index=out.index)
    )
    long_exit = (ema_exit | (low < trail_stop.shift(1))).fillna(False)

    out["hh"] = _as_series(hh).reindex(out.index)
    out["ema"] = _as_series(ema).reindex(out.index)
    out["atr"] = atr.reindex(out.index)
    out["trail_stop"] = _as_series(trail_stop).reindex(out.index)
    out["long_entry"] = long_entry
    out["long_exit"] = long_exit

    out["hh_buf"] = _as_series(hh_buf).reindex(out.index)
    out["trend_ok"] = trend_ok.fillna(False)
    out["trigger"] = trigger.fillna(False)
    out["atr_ok"] = atr.gt(0) & np.isfinite(atr)

    return out
