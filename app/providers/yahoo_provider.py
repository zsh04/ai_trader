from __future__ import annotations

import logging
import math
import random
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

import requests
from app.utils.http import http_get
from app.utils import env as ENV

log = logging.getLogger(__name__)

_CHUNK_SIZE = 50
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_YAHOO_BACKOFF = [0.5, 1.0, 2.0]

_breaker_lock = threading.Lock()
_breaker_failures = 0
_breaker_open_until = 0.0


def yahoo_is_degraded() -> bool:
    """
    Checks if the Yahoo provider is degraded.

    Returns:
        bool: True if the provider is degraded, False otherwise.
    """
    with _breaker_lock:
        return _breaker_open_until > time.monotonic()


def _breaker_allow_request() -> Tuple[bool, float]:
    """
    Checks if a request is allowed by the circuit breaker.

    Returns:
        Tuple[bool, float]: A tuple of (allowed, remaining_time).
    """
    with _breaker_lock:
        remaining = _breaker_open_until - time.monotonic()
        if remaining > 0:
            return False, remaining
        return True, 0.0


def _breaker_record_throttle() -> None:
    """Records a throttle event."""
    global _breaker_failures, _breaker_open_until
    with _breaker_lock:
        _breaker_failures += 1
        if _breaker_failures >= 5:
            _breaker_open_until = time.monotonic() + 60.0
            _breaker_failures = 0
            log.warning("yahoo provider circuit opened for 60s due to throttling")


def _breaker_record_success() -> None:
    """Records a successful request."""
    global _breaker_failures, _breaker_open_until
    with _breaker_lock:
        _breaker_failures = 0
        _breaker_open_until = 0.0


def _yahoo_request(url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
    """
    Makes a request to the Yahoo Finance API.

    Args:
        url (str): The URL to request.
        params (Optional[Dict[str, Any]]): The request parameters.

    Returns:
        Tuple[int, Dict[str, Any]]: A tuple of (status_code, response_data).
    """
    allowed, remaining = _breaker_allow_request()
    if not allowed:
        log.debug(
            "yahoo provider circuit open; skipping request (%.1fs remaining)",
            remaining,
        )
        return 503, {"error": "yahoo_circuit_open"}

    timeout = getattr(ENV, "HTTP_TIMEOUT_SECS", 10)
    headers = {"User-Agent": getattr(ENV, "HTTP_USER_AGENT", "ai-trader/1.0")}

    for attempt in range(len(_YAHOO_BACKOFF) + 1):
        try:
            resp = requests.get(
                url,
                params=params or {},
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            log.warning("yahoo request error attempt=%s url=%s error=%s", attempt + 1, url, exc)
            if attempt < len(_YAHOO_BACKOFF):
                sleep = _YAHOO_BACKOFF[attempt] * random.uniform(0.75, 1.25)
                time.sleep(sleep)
                continue
            return 599, {}

        text = resp.text or ""
        throttled = resp.status_code == 429 or "Edge: Too Many Requests" in text

        if throttled:
            log.warning(
                "yahoo throttled status=%s attempt=%s url=%s",
                resp.status_code,
                attempt + 1,
                url,
            )
            if attempt < len(_YAHOO_BACKOFF):
                sleep = _YAHOO_BACKOFF[attempt] * random.uniform(0.75, 1.25)
                time.sleep(sleep)
                continue
            _breaker_record_throttle()
            return resp.status_code or 429, {"error": "yahoo_throttled"}

        _breaker_record_success()

        if 200 <= resp.status_code < 300:
            try:
                return resp.status_code, resp.json()
            except Exception:
                log.debug("yahoo JSON decode failed for %s", url)
                return resp.status_code, {}

        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {}

    _breaker_record_throttle()
    return 429, {"error": "yahoo_throttled"}

if TYPE_CHECKING:
    from pandas import DataFrame


def _try_import_yf():
    """
    Tries to import the yfinance library.

    Returns:
        The yfinance library if successful, None otherwise.
    """
    try:
        import yfinance as yf
        return yf
    except Exception as e:
        log.warning(
            "yahoo_provider: yfinance not available (%s); returning empty results", e
        )
        return None


def _norm_syms(symbols: Iterable[str]) -> List[str]:
    """
    Normalizes a list of symbols.

    Args:
        symbols (Iterable[str]): A list of symbols.

    Returns:
        List[str]: A normalized list of symbols.
    """
    return [s.strip().upper() for s in symbols if s and s.strip()]


def _chunk(symbols: Iterable[str], n: int = _CHUNK_SIZE) -> List[List[str]]:
    """
    Chunks a list of symbols into smaller lists.

    Args:
        symbols (Iterable[str]): A list of symbols.
        n (int): The size of each chunk.

    Returns:
        List[List[str]]: A list of lists of symbols.
    """
    syms = _norm_syms(symbols)
    return [syms[i : i + n] for i in range(0, len(syms), n)]


def _coerce_date(value: str | date | datetime | None) -> date:
    """
    Coerces a value to a date.

    Args:
        value (str | date | datetime | None): The value to coerce.

    Returns:
        date: A date object.
    """
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
    """
    Converts a date to an epoch timestamp.

    Args:
        value (date): The date to convert.

    Returns:
        int: An epoch timestamp.
    """
    return int(
        datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp()
    )


def _safe_float(seq: Any, idx: int) -> Optional[float]:
    """
    Safely gets a float from a sequence.

    Args:
        seq (Any): The sequence.
        idx (int): The index.

    Returns:
        Optional[float]: The float value, or None if not found.
    """
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
    """
    Safely gets an integer from a sequence.

    Args:
        seq (Any): The sequence.
        idx (int): The index.

    Returns:
        Optional[int]: The integer value, or None if not found.
    """
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
    """
    Fetches chart history for a symbol.

    Args:
        symbol (str): The symbol to fetch.
        start (str | date): The start date.
        end (Optional[str | date]): The end date.
        auto_adjust (bool): Whether to auto-adjust for splits and dividends.

    Returns:
        Dict[str, Any]: The chart history.
    """
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
        timeout=getattr(ENV, "HTTP_TIMEOUT_SECS", 10),
        retries=getattr(ENV, "HTTP_RETRIES", 2),
        backoff=getattr(ENV, "HTTP_BACKOFF", [0.5, 1.0, 2.0]),
        headers={"User-Agent": getattr(ENV, "HTTP_USER_AGENT", "ai-trader/1.0")},
    )

    if status != 200:
        chart_err = ((data or {}).get("chart") or {}).get("error")
        log.warning(
            "yahoo history fetch failed status=%s symbol=%s start=%s end=%s error=%s",
            status,
            symbol,
            start,
            end,
            chart_err,
            extra={
                "provider": "yahoo",
                "op": "history",
                "status": status,
                "symbol": symbol.upper(),
            },
        )
        return {}
    return data or {}


def _chart_to_dataframe(payload: Dict[str, Any], auto_adjust: bool) -> "DataFrame":
    """
    Converts a chart payload to a DataFrame.

    Args:
        payload (Dict[str, Any]): The chart payload.
        auto_adjust (bool): Whether to auto-adjust for splits and dividends.

    Returns:
        DataFrame: A DataFrame with the chart data.
    """
    import pandas as pd

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
        l = _safe_float(quote.get("low"), idx)
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
                    if l is not None:
                        l *= factor

        rows.append(
            {
                "date": dt,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v or 0,
            }
        )

    if not rows:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows).set_index("date")
    return df[cols]


def intraday_last(symbols: List[str]) -> Dict[str, float]:
    """
    Gets the last intraday price for a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.

    Returns:
        Dict[str, float]: A dictionary of last prices.
    """
    yf = _try_import_yf()
    if not yf:
        return {}

    out: Dict[str, float] = {}
    for batch in _chunk(symbols):
        try:
            tkrs = yf.Tickers(" ".join(batch))
        except Exception as e:
            log.warning(
                "yahoo intraday_last: failed to build Tickers for %s: %s", batch, e
            )
            continue

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
                pass
            except Exception:
                pass

        missing = [s for s in batch if s not in out]
        if not missing:
            continue

        for sym in missing:
            try:
                t = tkrs.tickers[sym]
                df = t.history(
                    period="1d", interval="1m", prepost=True, auto_adjust=False
                )
                if not df.empty and "Close" in df.columns:
                    last = float(df["Close"].iloc[-1])
                    if last > 0:
                        out[sym] = last
            except Exception as e:
                log.debug("yahoo intraday_last: fallback failed for %s: %s", sym, e)

    return out


def latest_close(symbols: List[str]) -> Dict[str, float]:
    """
    Gets the latest close price for a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.

    Returns:
        Dict[str, float]: A dictionary of latest close prices.
    """
    yf = _try_import_yf()
    if not yf:
        return {}

    out: Dict[str, float] = {}
    for batch in _chunk(symbols):
        try:
            tkrs = yf.Tickers(" ".join(batch))
        except Exception as e:
            log.warning(
                "yahoo latest_close: failed to build Tickers for %s: %s", batch, e
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
                log.debug("yahoo latest_close: history failed for %s: %s", sym, e)
    return out


def latest_volume(symbols: List[str]) -> Dict[str, int]:
    """
    Gets the latest volume for a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.

    Returns:
        Dict[str, int]: A dictionary of latest volumes.
    """
    yf = _try_import_yf()
    if not yf:
        return {}

    out: Dict[str, int] = {}
    for batch in _chunk(symbols):
        try:
            tkrs = yf.Tickers(" ".join(batch))
        except Exception as e:
            log.warning(
                "yahoo latest_volume: failed to build Tickers for %s: %s", batch, e
            )
            continue

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
                pass
            except KeyError:
                pass
            except Exception:
                pass

        missing = [s for s in batch if s not in out]
        if not missing:
            continue

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
                log.debug(
                    "yahoo latest_volume: daily fallback failed for %s: %s", sym, e
                )

    return out


def get_history_daily(
    symbol: str,
    start: str | date,
    end: Optional[str | date] = None,
    auto_adjust: bool = False,
) -> "DataFrame":
    """
    Gets daily historical data for a symbol.

    Args:
        symbol (str): The symbol to get data for.
        start (str | date): The start date.
        end (Optional[str | date]): The end date.
        auto_adjust (bool): Whether to auto-adjust for splits and dividends.

    Returns:
        DataFrame: A DataFrame with the historical data.
    """
    payload = _fetch_chart_history(symbol, start, end, auto_adjust=auto_adjust)
    if payload:
        try:
            return _chart_to_dataframe(payload, auto_adjust=auto_adjust)
        except Exception as exc:
            log.warning(
                "yahoo history parse failed symbol=%s start=%s end=%s err=%s",
                symbol,
                start,
                end,
                exc,
            )

    yf = _try_import_yf()
    if not yf:
        import pandas as pd
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    import pandas as pd

    t = yf.Ticker(symbol.upper())
    df = t.history(
        start=start, end=end, interval="1d", prepost=False, auto_adjust=auto_adjust
    )
    if df.empty:
        return df

    cols = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    out = df.rename(columns=cols)[list(cols.values())].copy()

    try:
        idx = out.index
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
    except Exception:
        try:
            idx = out.index.tz_localize(None)
        except Exception:
            idx = out.index

    import pandas as pd

    out.index = pd.Index([d.date() for d in pd.to_datetime(idx)], name="date")
    return out
