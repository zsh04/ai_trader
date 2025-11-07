from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from app.dal.schemas import Bar, Bars
from app.dal.vendors.base import FetchRequest, VendorClient
from app.utils import env as ENV
from app.utils.http import http_get

try:  # pragma: no cover - optional dependency already shipped but guarded
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover - keep runtime resilient
    yf = None


_YAHOO_TZ = "America/New_York"
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class YahooVendor(VendorClient):
    """Yahoo Finance historical bars via yfinance with REST fallback."""

    def __init__(self, timezone_name: str = _YAHOO_TZ) -> None:
        super().__init__("yahoo")
        self.timezone_name = timezone_name

    def fetch_bars(self, request: FetchRequest) -> Bars:
        symbol = request.symbol.upper()
        bars = Bars(symbol=symbol, vendor=self.name, timezone=self.timezone_name)

        df = self._fetch_with_yfinance(symbol, request)
        if df is None or df.empty:
            df = self._fetch_with_chart_api(symbol, request)

        if df is None or df.empty:
            logger.debug(
                "yahoo vendor fetch returned no data symbol={} interval={} start={} end={} limit={}",
                symbol,
                request.interval,
                request.start,
                request.end,
                request.limit,
            )
            return bars

        normalized = self._normalize_dataframe(df)
        if normalized.empty:
            return bars

        for ts, row in normalized.iterrows():
            ts_utc = self._ensure_utc_timestamp(ts)
            open_px = self._coerce_float(row.get("open"))
            high_px = self._coerce_float(row.get("high"))
            low_px = self._coerce_float(row.get("low"))
            close_px = self._coerce_float(row.get("close"))
            volume = self._coerce_float(row.get("volume"), allow_zero=True)
            if close_px is None:
                continue
            bars.append(
                Bar(
                    symbol=symbol,
                    vendor=self.name,
                    timestamp=ts_utc,
                    open=open_px or 0.0,
                    high=high_px or 0.0,
                    low=low_px or 0.0,
                    close=close_px,
                    volume=volume or 0.0,
                    timezone=self.timezone_name,
                    source="historical",
                )
            )

        return bars

    # ------------------------------------------------------------------
    # yfinance path
    # ------------------------------------------------------------------

    def _fetch_with_yfinance(
        self, symbol: str, request: FetchRequest
    ) -> Optional[pd.DataFrame]:
        if yf is None:
            return None

        interval = _map_interval(request.interval)
        if interval is None:
            return None

        history_kwargs: Dict[str, Any] = {
            "interval": interval,
            "prepost": True,
            "auto_adjust": False,
        }

        start = _naive_utc(request.start)
        end = _naive_utc(request.end)

        if start is not None:
            history_kwargs["start"] = start
        if end is not None:
            history_kwargs["end"] = end

        if "start" not in history_kwargs and "end" not in history_kwargs:
            history_kwargs["period"] = _default_period(interval, request.limit)

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(**history_kwargs)
        except Exception as exc:  # pragma: no cover - network/pathological errors
            logger.debug(
                "yahoo vendor yfinance failure symbol={} error={}", symbol, exc
            )
            return None

        if df is None or df.empty:
            return None

        if request.limit:
            df = df.tail(int(request.limit))
        return df

    # ------------------------------------------------------------------
    # REST fallback (daily bars only)
    # ------------------------------------------------------------------

    def _fetch_with_chart_api(
        self, symbol: str, request: FetchRequest
    ) -> Optional[pd.DataFrame]:
        interval = _map_interval(request.interval)
        if interval not in {"1d", "1Day", "1day"}:
            return None

        start_date = (
            _coerce_date(request.start)
            or (datetime.now(timezone.utc) - timedelta(days=365)).date()
        )
        end_date = _coerce_date(request.end) or datetime.now(timezone.utc).date()
        if end_date <= start_date:
            end_date = start_date + timedelta(days=1)

        payload = _fetch_chart_history(symbol, start_date, end_date, auto_adjust=False)
        if not payload:
            return None

        df = _chart_payload_to_dataframe(payload, auto_adjust=False)
        if df.empty:
            return None

        if request.limit:
            df = df.tail(int(request.limit))

        # Chart API returns date index that may be naive or already tz-aware.
        df.index = pd.to_datetime(df.index)
        try:
            if getattr(df.index, "tz", None) is None:
                df.index = df.index.tz_localize(self.timezone_name)
            else:
                df.index = df.index.tz_convert(self.timezone_name)
        except TypeError as exc:  # pragma: no cover - pandas edge case
            logger.debug(
                "yahoo chart index localization failed symbol={} error={}",
                symbol,
                exc,
            )
        return df

    # ------------------------------------------------------------------
    # Data shaping helpers
    # ------------------------------------------------------------------

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {col: col.lower() for col in df.columns}
        normalized = df.rename(columns=rename_map)
        cols = ["open", "high", "low", "close", "volume"]
        for col in cols:
            if col not in normalized.columns:
                normalized[col] = float("nan")
        out = normalized[cols].copy()
        out = out.replace({pd.NA: float("nan")})
        return out

    def _ensure_utc_timestamp(self, ts: Any) -> datetime:
        if isinstance(ts, pd.Timestamp):
            if ts.tzinfo is None:
                ts = ts.tz_localize(self.timezone_name)
            return ts.tz_convert(timezone.utc).to_pydatetime()
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        parsed = pd.Timestamp(ts)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize(self.timezone_name)
        return parsed.tz_convert(timezone.utc).to_pydatetime()

    @staticmethod
    def _coerce_float(value: Any, *, allow_zero: bool = False) -> Optional[float]:
        if value is None:
            return None
        try:
            num = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(num):
            return None
        if not allow_zero and num == 0.0:
            return None
        return num


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------


def _map_interval(interval: str | None) -> Optional[str]:
    if not interval:
        return "1d"
    lookup = {
        "1m": "1m",
        "1min": "1m",
        "1Min": "1m",
        "5m": "5m",
        "5min": "5m",
        "5Min": "5m",
        "15m": "15m",
        "15Min": "15m",
        "30m": "30m",
        "30Min": "30m",
        "60m": "60m",
        "1h": "60m",
        "1H": "60m",
        "1hour": "60m",
        "1Hour": "60m",
        "1d": "1d",
        "1day": "1d",
        "1D": "1d",
        "1Day": "1d",
        "1wk": "1wk",
        "1W": "1wk",
        "1week": "1wk",
        "1mo": "1mo",
        "1M": "1mo",
        "1month": "1mo",
    }
    return lookup.get(interval, "1d")


def _default_period(interval: str, limit: Optional[int]) -> str:
    # yfinance requires small windows for intraday data; expand for daily.
    if interval == "1m":
        return "5d"
    if interval in {"5m", "15m", "30m", "60m"}:
        return "1mo"
    if interval in {"1wk", "1mo"}:
        return "max"
    if limit and limit <= 30:
        return "1mo"
    if limit and limit <= 365:
        return "1y"
    return "max"


def _naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _coerce_date(value: Optional[datetime | date]) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date()
    return None


def _epoch_for_day(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def _fetch_chart_history(
    symbol: str,
    start: date,
    end: date,
    *,
    auto_adjust: bool = False,
) -> Dict[str, Any]:
    params = {
        "interval": "1d",
        "events": "div,splits",
        "includeAdjustedClose": "true" if auto_adjust else "false",
        "period1": str(_epoch_for_day(start)),
        "period2": str(_epoch_for_day(end + timedelta(days=1))),
    }

    status, data = http_get(
        _YAHOO_CHART_URL.format(symbol=symbol.upper()),
        params=params,
        timeout=ENV.HTTP_TIMEOUT,
        retries=ENV.HTTP_RETRIES,
        backoff=ENV.HTTP_BACKOFF,
        headers={"User-Agent": ENV.HTTP_USER_AGENT},
    )

    if status != 200:
        chart_err = ((data or {}).get("chart") or {}).get("error")
        logger.bind(provider="yahoo", op="history", status=status).warning(
            "yahoo chart history failed symbol={} status={} error={}",
            symbol,
            status,
            chart_err,
        )
        return {}
    return data or {}


def _chart_payload_to_dataframe(
    payload: Dict[str, Any], *, auto_adjust: bool
) -> pd.DataFrame:
    chart = payload.get("chart") or {}
    result = chart.get("result") or []
    if not result:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

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
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (OSError, TypeError, ValueError) as exc:
            logger.debug(
                "yahoo chart payload timestamp parse failed index=%s value=%s error=%s",
                idx,
                ts,
                exc,
            )
            continue

        open_px = _safe_list_float(quote.get("open"), idx)
        high_px = _safe_list_float(quote.get("high"), idx)
        low_px = _safe_list_float(quote.get("low"), idx)
        close_px = _safe_list_float(quote.get("close"), idx)
        volume = _safe_list_int(quote.get("volume"), idx) or 0
        if close_px is None:
            continue

        if auto_adjust and adjclose_seq:
            adj_close = _safe_list_float(adjclose_seq, idx)
            if adj_close and close_px:
                factor = adj_close / close_px if close_px else None
                close_px = adj_close
                if factor:
                    if open_px is not None:
                        open_px *= factor
                    if high_px is not None:
                        high_px *= factor
                    if low_px is not None:
                        low_px *= factor

        rows.append(
            {
                "timestamp": dt,
                "open": open_px,
                "high": high_px,
                "low": low_px,
                "close": close_px,
                "volume": volume,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows).set_index("timestamp")
    return df


def _safe_list_float(seq: Any, idx: int) -> Optional[float]:
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


def _safe_list_int(seq: Any, idx: int) -> Optional[int]:
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


__all__ = ["YahooVendor"]
