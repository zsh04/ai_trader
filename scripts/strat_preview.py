#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

# Try to import your provider; otherwise fallback
try:
    from app.providers.yahoo_provider import get_history_daily as load_daily  # type: ignore
except Exception:
    load_daily = None  # type: ignore

from app.strats import (
    BreakoutParams,
    MomentumParams,
    breakout_signals,
    momentum_signals,
)
from app.logging_utils import setup_logging


log = logger


def _load_data(symbol: str, start: str | None, end: str | None) -> pd.DataFrame:
    if load_daily is not None:
        return load_daily(symbol, start=start, end=end)

    # Fallback to yfinance if present
    try:
        import yfinance as yf  # type: ignore

        df = yf.download(
            symbol, start=start, end=end, auto_adjust=False, progress=False
        )
        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )[["open", "high", "low", "close", "volume"]]
        return df.dropna().astype(
            {"open": float, "high": float, "low": float, "close": float, "volume": int}
        )
    except Exception:
        pass

    # Final synthetic fallback
    idx = pd.date_range(start or "2021-01-01", end or date.today(), freq="B")
    price = pd.Series(
        np.cumprod(1 + np.random.normal(0.0006, 0.01, len(idx))) * 100, index=idx
    )
    high = price * (1 + np.random.uniform(0.0, 0.01, len(idx)))
    low = price * (1 - np.random.uniform(0.0, 0.01, len(idx)))
    open_ = price.shift(1).fillna(price.iloc[0])
    vol = (np.random.randint(1e6, 5e6, len(idx))).astype(int)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": price, "volume": vol},
        index=idx,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview breakout & momentum signals")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--csv", type=Path, help="Optional path to write merged outputs")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    setup_logging(force=True, level="DEBUG" if args.debug else "INFO")

    log.info("Loading %s from %s → %s", args.symbol, args.start, args.end or "today")
    df = _load_data(args.symbol, args.start, args.end)

    # Run strategies
    bparams = BreakoutParams()
    mparams = MomentumParams()

    b = breakout_signals(df, bparams).add_prefix("brk_")
    m = momentum_signals(df, mparams).add_prefix("mom_")

    merged = df.join([b, m], how="left")

    # Quick summary
    b_entries = int(merged["brk_long_entry"].sum())
    b_exits = int(merged["brk_long_exit"].sum())
    m_entries = int(merged["mom_long_entry"].sum())
    m_exits = int(merged["mom_long_exit"].sum())

    log.info(
        "[%s] breakout entries=%d exits=%d | momentum entries=%d exits=%d",
        args.symbol,
        b_entries,
        b_exits,
        m_entries,
        m_exits,
    )

    print("\nLast 5 rows (selected):")
    cols = [
        "close",
        "brk_hh",
        "brk_ema",
        "brk_long_entry",
        "brk_long_exit",
        "mom_momentum",
        "mom_ema",
        "mom_rank",
        "mom_long_entry",
        "mom_long_exit",
    ]
    print(merged[cols].tail(5).to_string())

    if args.csv:
        merged.to_csv(args.csv)
        log.info("Wrote merged output to %s", args.csv)


if __name__ == "__main__":
    main()
