from __future__ import annotations

import math
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

import requests
from loguru import logger

from app.utils import env as ENV
from app.utils.http import compute_backoff_delay, http_get

# yfinance is optional at runtime; we guard imports and degrade gracefully.

if TYPE_CHECKING:  # pragma: no cover - typing helper
    import pandas as pd

    DataFrame = pd.DataFrame
else:
    DataFrame = Any

_CHUNK_SIZE = 50  # keep multi-symbol batches reasonable
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_breaker_lock = threading.Lock()
_breaker_failures = 0
_breaker_open_until = 0.0


def yahoo_is_degraded() -> bool:
    """Return True if the Yahoo provider circuit breaker is open."""
    with _breaker_lock:
        return _breaker_open_until > time.monotonic()


def _breaker_allow_request() -> Tuple[bool, float]:
    with _breaker_lock:
        remaining = _breaker_open_until - time.monotonic()
        if remaining > 0:
            return False, remaining
        return True, 0.0


def _breaker_record_throttle() -> None:
    global _breaker_failures, _breaker_open_until
    with _breaker_lock:
        _breaker_failures += 1
        if _breaker_failures >= 5:
            _breaker_open_until = time.monotonic() + 60.0
            _breaker_failures = 0
            logger.warning("yahoo provider circuit opened for 60s due to throttling")


def _breaker_record_success() -> None:
    global _breaker_failures, _breaker_open_until
    with _breaker_lock:
        _breaker_failures = 0
        _breaker_open_until = 0.0


def _yahoo_request(
    url: str, params: Optional[Dict[str, Any]] = None
) -> Tuple[int, Dict[str, Any]]:
    allowed, remaining = _breaker_allow_request()
    if not allowed:
        logger.debug(
            "yahoo provider circuit open; skipping request ({:.1f}s remaining)",
            remaining,
        )
        return 503, {"error": "yahoo_circuit_open"}

    timeout = float(getattr(ENV, "HTTP_TIMEOUT", getattr(ENV, "HTTP_TIMEOUT_SECS", 10)))
    retries = max(0, int(getattr(ENV, "HTTP_RETRIES", 2)))
    backoff = float(
        getattr(ENV, "HTTP_BACKOFF", getattr(ENV, "HTTP_RETRY_BACKOFF_SEC", 1.5))
    )
    headers = {"User-Agent": getattr(ENV, "HTTP_USER_AGENT", "ai-trader/1.0")}

    last_status = 0
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url,
                params=params or {},
                headers=headers,
                timeout=timeout,
            )
            last_status = resp.status_code
        except requests.RequestException as exc:
            logger.warning(
                "yahoo request error attempt={} url={} error={}", attempt + 1, url, exc
            )
            if attempt < retries:
                sleep = compute_backoff_delay(attempt, backoff, None)
                time.sleep(sleep)
                continue
            return 599, {}

        text = resp.text or ""
        throttled = resp.status_code == 429 or "Edge: Too Many Requests" in text

        if throttled:
            logger.warning(
                "yahoo throttled status={} attempt={} url={}",
                resp.status_code,
                attempt + 1,
                url,
            )
            if attempt < retries:
                sleep = compute_backoff_delay(
                    attempt, backoff, resp.headers.get("Retry-After")
                )
                time.sleep(sleep)
                continue
            _breaker_record_throttle()
            return resp.status_code or 429, {"error": "yahoo_throttled"}

        _breaker_record_success()

        if 200 <= resp.status_code < 300:
            try:
                return resp.status_code, resp.json()
            except Exception:
                logger.debug("yahoo JSON decode failed for {}", url)
                return resp.status_code, {}

        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {}

    _breaker_record_throttle()
    status = last_status or 429
    return status, {"error": "yahoo_throttled"}


if TYPE_CHECKING:
    # for type hints without importing pandas at runtime
    from pandas import DataFrame  # noqa: F401


def _try_import_yf():
    try:
        import yfinance as yf  # type: ignore

        return yf
    except Exception as e:
        logger.warning(
            "yahoo_provider: yfinance not available ({}); returning empty results", e
        )
        return None


def _norm_syms(symbols: Iterable[str]) -> List[str]:
    return [s.strip().upper() for s in symbols if s and s.strip()]


def _chunk(symbols: Iterable[str], n: int = _CHUNK_SIZE) -> List[List[str]]:
    syms = _norm_syms(symbols)
    return [syms[i : i + n] for i in range(0, len(syms), n)]


def _coerce_date(value: str | date | datetime | None) -> date:
    if value is None:
        return datetime.now(timezone.utc).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return date.fromisoformat(str(value).split("T", 1)[0])


def _epoch_for_day(value: date) -> int:
    return int(
        datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp()
    )


def _safe_float(seq: Any, idx: int) -> Optional[float]:
    if not isinstance(seq, list):
        return None
    try:
        val = seq[idx]
    except (IndexError, TypeError):
        return None
    if val is None:
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(num):
        return None
    return num


def _safe_int(seq: Any, idx: int) -> Optional[int]:
    if not isinstance(seq, list):
        return None
    try:
        val = seq[idx]
    except (IndexError, TypeError):
        return None
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            return int(float(val))
        except Exception:
            return None


def _fetch_chart_history(
    symbol: str,
    start: str | date,
    end: Optional[str | date] = None,
    *,
    auto_adjust: bool = False,
) -> Dict[str, Any]:
    start_day = _coerce_date(start)
    end_day = _coerce_date(end) if end else datetime.now(timezone.utc).date()
    if end_day <= start_day:
        end_day = start_day + timedelta(days=1)
    period1 = _epoch_for_day(start_day)
    period2 = _epoch_for_day(end_day + timedelta(days=1))

    params = {
        "interval": "1d",
        "events": "div,splits",
        "includeAdjustedClose": "true" if auto_adjust else "false",
        "period1": str(period1),
        "period2": str(period2),
    }

    status, data = http_get(
        _YAHOO_CHART_URL.format(symbol=symbol.upper()),
        params=params,
        timeout=getattr(ENV, "HTTP_TIMEOUT", getattr(ENV, "HTTP_TIMEOUT_SECS", 10)),
        retries=getattr(ENV, "HTTP_RETRIES", 2),
        backoff=getattr(
            ENV, "HTTP_BACKOFF", getattr(ENV, "HTTP_RETRY_BACKOFF_SEC", 1.5)
        ),
        headers={"User-Agent": getattr(ENV, "HTTP_USER_AGENT", "ai-trader/1.0")},
    )

    if status != 200:
        chart_err = ((data or {}).get("chart") or {}).get("error")
        logger.bind(
            provider="yahoo",
            op="history",
            status=status,
            symbol=symbol.upper(),
        ).warning(
            "yahoo history fetch failed status={} symbol={} start={} end={} error={}",
            status,
            symbol,
            start,
            end,
            chart_err,
        )
        return {}
    return data or {}


def _chart_to_dataframe(payload: Dict[str, Any], auto_adjust: bool) -> DataFrame:
    import pandas as pd  # local import to avoid hard dependency at module load

    cols = ["open", "high", "low", "close", "volume"]
    chart = payload.get("chart") or {}
    result = chart.get("result") or []
    if not result:
        return pd.DataFrame(columns=cols)

    node = result[0] or {}
    timestamps = node.get("timestamp") or []
    indicators = node.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0] or {}
    adjclose_seq = (
        ((indicators.get("adjclose") or [{}])[0].get("adjclose") or [])
        if auto_adjust
        else []
    )

    rows = []
    for idx, ts in enumerate(timestamps):
        try:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        except Exception:
            continue

        o = _safe_float(quote.get("open"), idx)
        h = _safe_float(quote.get("high"), idx)
        low_val = _safe_float(quote.get("low"), idx)
        c = _safe_float(quote.get("close"), idx)
        v = _safe_int(quote.get("volume"), idx)
        if c is None:
            continue

        if auto_adjust and adjclose_seq:
            adj_close = _safe_float(adjclose_seq, idx)
            if adj_close and c:
                factor = adj_close / c if c else None
                c = adj_close
                if factor:
                    if o is not None:
                        o *= factor
                    if h is not None:
                        h *= factor
                    if low_val is not None:
                        low_val *= factor

        rows.append(
            {
                "date": dt,
                "open": o,
                "high": h,
                "low": low_val,
                "close": c,
                "volume": v or 0,
            }
        )

    if not rows:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows).set_index("date")
    return df[cols]


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
            logger.warning(
                "yahoo intraday_last: failed to build Tickers for {}: {}", batch, e
            )
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
                df = t.history(
                    period="1d", interval="1m", prepost=True, auto_adjust=False
                )
                if not df.empty and "Close" in df.columns:
                    last = float(df["Close"].iloc[-1])
                    if last > 0:
                        out[sym] = last
            except Exception as e:
                logger.debug("yahoo intraday_last: fallback failed for {}: {}", sym, e)

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
            logger.warning(
                "yahoo latest_close: failed to build Tickers for {}: {}", batch, e
            )
            continue

        for sym in batch:
            try:
                t = tkrs.tickers[sym]
                df = t.history(
                    period="5d", interval="1d", prepost=False, auto_adjust=False
                )
                if not df.empty and "Close" in df.columns:
                    c = float(df["Close"].iloc[-1])
                    if c > 0:
                        out[sym] = c
            except Exception as e:
                logger.debug("yahoo latest_close: history failed for {}: {}", sym, e)
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
            logger.warning(
                "yahoo latest_volume: failed to build Tickers for {}: {}", batch, e
            )
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
                df = t.history(
                    period="1d", interval="1m", prepost=True, auto_adjust=False
                )
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
                df = t.history(
                    period="5d", interval="1d", prepost=False, auto_adjust=False
                )
                if not df.empty and "Volume" in df.columns:
                    v = int(df["Volume"].iloc[-1] or 0)
                    if v > 0:
                        out[sym] = v
            except Exception as e:
                logger.debug(
                    "yahoo latest_volume: daily fallback failed for {}: {}", sym, e
                )

    return out


# --- History helpers for backtests ----------------------------------------------------


def get_history_daily(
    symbol: str,
    start: str | date,
    end: Optional[str | date] = None,
    auto_adjust: bool = False,
) -> DataFrame:
    """
    Daily OHLCV for one symbol. Returns a DataFrame with columns:
    [open, high, low, close, volume] and a Date index (naive).
    """
    payload = _fetch_chart_history(symbol, start, end, auto_adjust=auto_adjust)
    if payload:
        try:
            return _chart_to_dataframe(payload, auto_adjust=auto_adjust)
        except Exception as exc:  # pragma: no cover - extremely rare parsing bug
            logger.warning(
                "yahoo history parse failed symbol={} start={} end={} err={}",
                symbol,
                start,
                end,
                exc,
            )

    yf = _try_import_yf()
    if not yf:
        import pandas as pd  # local import to keep module importable without pandas

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    import pandas as pd

    t = yf.Ticker(symbol.upper())
    df = t.history(
        start=start, end=end, interval="1d", prepost=False, auto_adjust=auto_adjust
    )
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
