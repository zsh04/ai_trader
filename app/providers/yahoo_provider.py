from __future__ import annotations

import logging
import math
from datetime import date
from typing import TYPE_CHECKING
from typing import Any, Dict, Iterable, List, Optional, Tuple

# yfinance is optional at runtime; we guard imports and degrade gracefully.
log = logging.getLogger(__name__)

_CHUNK_SIZE = 50  # keep multi-symbol batches reasonable

if TYPE_CHECKING:
    # for type hints without importing pandas at runtime
    from pandas import DataFrame  # noqa: F401


def _try_import_yf():
    try:
        import yfinance as yf  # type: ignore
        return yf
    except Exception as e:
        log.warning("yahoo_provider: yfinance not available (%s); returning empty results", e)
        return None


def _norm_syms(symbols: Iterable[str]) -> List[str]:
    return [s.strip().upper() for s in symbols if s and s.strip()]


def _chunk(symbols: Iterable[str], n: int = _CHUNK_SIZE) -> List[List[str]]:
    syms = _norm_syms(symbols)
    return [syms[i : i + n] for i in range(0, len(syms), n)]


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def intraday_last(symbols: List[str]) -> Dict[str, float]:
    """
    Best-effort last price using Yahoo fast_info when available, falling back to a
    fresh 1m candle if necessary. Returns {SYM: last_price}.
    """
    yf = _try_import_yf()
    if not yf:
        return {}

    out: Dict[str, float] = {}
    for batch in _chunk(symbols):
        try:
            tkrs = yf.Tickers(" ".join(batch))
        except Exception as e:
            log.warning("yahoo intraday_last: failed to build Tickers for %s: %s", batch, e)
            continue

        # First pass: fast_info (cheap)
        for sym in batch:
            try:
                t = tkrs.tickers[sym]
                fi = getattr(t, "fast_info", None)
                px_raw = fi.get("last_price") if fi else None
                if px_raw is not None:
                    px = float(px_raw)
                    if not math.isnan(px) and px > 0:
                        out[sym] = px
            except KeyError:
                # fast_info present but missing key
                pass
            except Exception:
                # ignore; try a slower fallback below
                pass

        # Fallback only for the ones we still don't have
        missing = [s for s in batch if s not in out]
        if not missing:
            continue

        for sym in missing:
            try:
                t = tkrs.tickers[sym]
                # Small download; 1d/1m includes today’s intraday bars
                df = t.history(period="1d", interval="1m", prepost=True, auto_adjust=False)
                if not df.empty and "Close" in df.columns:
                    last = float(df["Close"].iloc[-1])
                    if last > 0:
                        out[sym] = last
            except Exception as e:
                log.debug("yahoo intraday_last: fallback failed for %s: %s", sym, e)

    return out


def latest_close(symbols: List[str]) -> Dict[str, float]:
    """
    Latest daily close for each symbol. Uses a small daily window and takes the last close.
    Returns {SYM: close}.
    """
    yf = _try_import_yf()
    if not yf:
        return {}

    out: Dict[str, float] = {}
    for batch in _chunk(symbols):
        try:
            tkrs = yf.Tickers(" ".join(batch))
        except Exception as e:
            log.warning("yahoo latest_close: failed to build Tickers for %s: %s", batch, e)
            continue

        for sym in batch:
            try:
                t = tkrs.tickers[sym]
                df = t.history(period="5d", interval="1d", prepost=False, auto_adjust=False)
                if not df.empty and "Close" in df.columns:
                    c = float(df["Close"].iloc[-1])
                    if c > 0:
                        out[sym] = c
            except Exception as e:
                log.debug("yahoo latest_close: history failed for %s: %s", sym, e)
    return out


def latest_volume(symbols: List[str]) -> Dict[str, int]:
    """
    Latest (most recent) volume. Tries fast_info first, then falls back to the latest
    intraday bar’s Volume, then daily Volume. Returns {SYM: volume}.
    """
    yf = _try_import_yf()
    if not yf:
        return {}

    out: Dict[str, int] = {}
    for batch in _chunk(symbols):
        try:
            tkrs = yf.Tickers(" ".join(batch))
        except Exception as e:
            log.warning("yahoo latest_volume: failed to build Tickers for %s: %s", batch, e)
            continue

        # fast_info volume (can be daily)
        for sym in batch:
            try:
                t = tkrs.tickers[sym]
                fi = getattr(t, "fast_info", None)
                v_raw = fi.get("last_volume") if fi else None
                if v_raw is not None:
                    v = int(float(v_raw))
                    if v > 0:
                        out[sym] = v
            except (ValueError, TypeError):
                # e.g., NaN / non-numeric
                pass
            except KeyError:
                pass
            except Exception:
                pass

        missing = [s for s in batch if s not in out]
        if not missing:
            continue

        # Try intraday 1m volume for the rest
        for sym in missing:
            try:
                t = tkrs.tickers[sym]
                df = t.history(period="1d", interval="1m", prepost=True, auto_adjust=False)
                if not df.empty and "Volume" in df.columns:
                    v = int(df["Volume"].iloc[-1] or 0)
                    if v > 0:
                        out[sym] = v
            except Exception:
                pass

        # Still missing? Use latest daily volume
        missing = [s for s in batch if s not in out]
        for sym in missing:
            try:
                t = tkrs.tickers[sym]
                df = t.history(period="5d", interval="1d", prepost=False, auto_adjust=False)
                if not df.empty and "Volume" in df.columns:
                    v = int(df["Volume"].iloc[-1] or 0)
                    if v > 0:
                        out[sym] = v
            except Exception as e:
                log.debug("yahoo latest_volume: daily fallback failed for %s: %s", sym, e)

    return out


# --- History helpers for backtests ----------------------------------------------------

def get_history_daily(
    symbol: str,
    start: str | date,
    end: Optional[str | date] = None,
    auto_adjust: bool = False,
) -> "pandas.DataFrame":
    """
    Daily OHLCV for one symbol. Returns a DataFrame with columns:
    [open, high, low, close, volume] and a Date index (naive).
    """
    yf = _try_import_yf()
    if not yf:
        import pandas as pd  # local import to keep module importable without pandas
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    import pandas as pd

    t = yf.Ticker(symbol.upper())
    df = t.history(start=start, end=end, interval="1d", prepost=False, auto_adjust=auto_adjust)
    if df.empty:
        return df

    # Normalize to expected schema for our backtester
    cols = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    out = df.rename(columns=cols)[list(cols.values())].copy()

    # Convert to date index robustly (handle tz-aware/naive)
    try:
        idx = out.index
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
    except Exception:
        try:
            idx = out.index.tz_localize(None)
        except Exception:
            idx = out.index  # leave as-is

    # Build a plain Date index
    import pandas as pd  # local import
    out.index = pd.Index([d.date() for d in pd.to_datetime(idx)], name="date")
    return out