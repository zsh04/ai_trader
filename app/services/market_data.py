from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import requests

from app.adapters.market.alpaca_client import AlpacaAuthError, AlpacaMarketClient
from app.utils import env as ENV

try:  # optional dependency for redundancy
    import yfinance as yf  # type: ignore
except ImportError:  # pragma: no cover
    yf = None

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
FINNHUB_URL = "https://finnhub.io/api/v1"
TWELVEDATA_URL = "https://api.twelvedata.com"


Snapshot = Dict[str, Dict[str, Optional[float]]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _parse_timestamp(value: object) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        candidate = candidate.replace(" ", "T")
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            try:
                dt = datetime.strptime(candidate, "%Y-%m-%dT%H:%M:%S")
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None
    return None


def _alpha_quote(symbols: Sequence[str]) -> Tuple[Dict[str, Snapshot], Optional[str]]:
    api_key = getattr(ENV, "ALPHAVANTAGE_API_KEY", "")
    if not api_key:
        return {}, None
    out: Dict[str, Snapshot] = {}
    for sym in symbols:
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": sym,
            "apikey": api_key,
        }
        try:
            resp = requests.get(ALPHAVANTAGE_URL, params=params, timeout=ENV.HTTP_TIMEOUT)
            payload = resp.json().get("Global Quote", {}) if resp.status_code == 200 else {}
            price = float(payload.get("05. price", "nan")) if payload else float("nan")
            if not payload or np.isnan(price):
                continue
            out[sym] = {
                "latestTrade": {
                    "price": price,
                    "timestamp": payload.get("07. latest trading day") or _now_iso(),
                },
                "dailyBar": {
                    "o": float(payload.get("02. open", "nan")),
                    "c": price,
                    "h": float(payload.get("03. high", "nan")),
                    "l": float(payload.get("04. low", "nan")),
                },
            }
        except Exception:
            continue
    note = "Alpha Vantage" if out else None
    return out, note


def _finnhub_quote(symbols: Sequence[str]) -> Tuple[Dict[str, Snapshot], Optional[str]]:
    api_key = os.getenv("FINNHUB_API_KEY") or getattr(ENV, "FINNHUB_API_KEY", "")
    if not api_key:
        return {}, None
    out: Dict[str, Snapshot] = {}
    for sym in symbols:
        try:
            resp = requests.get(
                f"{FINNHUB_URL}/quote",
                params={"symbol": sym, "token": api_key},
                timeout=ENV.HTTP_TIMEOUT,
            )
            data = resp.json() if resp.status_code == 200 else {}
            price = data.get("c")
            if price in (None, 0):
                continue
            out[sym] = {
                "latestTrade": {
                    "price": float(price),
                    "timestamp": (
                        datetime.fromtimestamp(data.get("t", 0), tz=timezone.utc).isoformat()
                        if data.get("t")
                        else _now_iso()
                    ),
                },
                "dailyBar": {
                    "o": float(data.get("o", 0.0)),
                    "c": float(price),
                    "h": float(data.get("h", 0.0)),
                    "l": float(data.get("l", 0.0)),
                },
            }
        except Exception:
            continue
    note = "Finnhub" if out else None
    return out, note


def _twelvedata_quote(symbols: Sequence[str]) -> Tuple[Dict[str, Snapshot], Optional[str]]:
    api_key = os.getenv("TWELVEDATA_API_KEY") or getattr(ENV, "TWELVEDATA_API_KEY", "")
    if not api_key:
        return {}, None
    out: Dict[str, Snapshot] = {}
    for sym in symbols:
        try:
            resp = requests.get(
                f"{TWELVEDATA_URL}/quote",
                params={"symbol": sym, "apikey": api_key},
                timeout=ENV.HTTP_TIMEOUT,
            )
            data = resp.json() if resp.status_code == 200 else {}
            price = data.get("close")
            if price in (None, ""):
                continue
            ts = data.get("datetime")
            parsed_ts = _parse_timestamp(ts)
            out[sym] = {
                "latestTrade": {
                    "price": float(price),
                    "timestamp": (parsed_ts or datetime.now(timezone.utc)).isoformat(),
                },
                "dailyBar": {
                    "o": float(data.get("open", 0.0)),
                    "c": float(price),
                    "h": float(data.get("high", 0.0)),
                    "l": float(data.get("low", 0.0)),
                },
            }
        except Exception:
            continue
    note = "Twelve Data" if out else None
    return out, note


def _yahoo_quote(symbols: Sequence[str]) -> Tuple[Dict[str, Snapshot], Optional[str]]:
    if yf is None:
        return {}, None
    out: Dict[str, Snapshot] = {}
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            info = ticker.fast_info
            price = info.get("lastPrice") or info.get("last_price")
            if price in (None, 0):
                continue
            out[sym] = {
                "latestTrade": {"price": float(price), "timestamp": _now_iso()},
                "dailyBar": {
                    "o": float(info.get("open", 0.0)),
                    "c": float(price),
                    "h": float(info.get("dayHigh", 0.0)),
                    "l": float(info.get("dayLow", 0.0)),
                },
            }
        except Exception:
            continue
    note = "Yahoo Finance" if out else None
    return out, note


def _alpaca_quote(symbols: Sequence[str]) -> Tuple[Dict[str, Snapshot], Optional[str]]:
    try:
        client = AlpacaMarketClient()
    except Exception:
        return {}, None
    out: Dict[str, Snapshot] = {}
    for sym in symbols:
        try:
            status, payload = client.snapshots([sym])
            if status != 200:
                continue
            snap = (payload or {}).get(sym)
            if not snap:
                continue
            trade = snap.get("latestTrade") or {}
            bar = snap.get("dailyBar") or {}
            price = trade.get("price") or bar.get("c")
            if price is None:
                continue
            out[sym] = {
                "latestTrade": {
                    "price": float(price),
                    "timestamp": trade.get("timestamp") or _now_iso(),
                },
                "dailyBar": {
                    "o": float(bar.get("o", 0.0)),
                    "c": float(price),
                    "h": float(bar.get("h", 0.0)),
                    "l": float(bar.get("l", 0.0)),
                },
            }
        except AlpacaAuthError:
            break
        except Exception:
            continue
    note = "Alpaca" if out else None
    return out, note


def get_market_snapshots(symbols: Iterable[str]) -> Tuple[Dict[str, Snapshot], str]:
    ordered = [_clean_symbol(sym) for sym in symbols if sym]
    remaining = [sym for sym in ordered if sym]
    snapshots: Dict[str, Snapshot] = {}
    provenance: Dict[str, str] = {}
    notes: List[str] = []

    providers = [
        ("Alpha Vantage", _alpha_quote),
        ("Finnhub", _finnhub_quote),
        ("Twelve Data", _twelvedata_quote),
        ("Yahoo Finance", _yahoo_quote),
        ("Alpaca", _alpaca_quote),
    ]

    for label, fetcher in providers:
        missing = [sym for sym in remaining if sym not in snapshots]
        if not missing:
            break
        data, provider_note = fetcher(missing)
        if not data:
            continue
        for sym, payload in data.items():
            if sym in snapshots:
                continue
            snapshots[sym] = payload
            provenance[sym] = label
        if provider_note:
            notes.append(provider_note)

    if not snapshots:
        return {}, "No data"

    ordered_labels = list(dict.fromkeys(provenance.values()))
    summary = " / ".join(ordered_labels)
    return snapshots, summary


def _alpha_bars(symbol: str, interval: str) -> Optional[pd.DataFrame]:
    api_key = getattr(ENV, "ALPHAVANTAGE_API_KEY", "")
    if not api_key:
        return None
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "apikey": api_key,
        "outputsize": "compact",
    }
    try:
        resp = requests.get(ALPHAVANTAGE_URL, params=params, timeout=ENV.HTTP_TIMEOUT)
        if resp.status_code != 200:
            return None
        key = next((k for k in resp.json().keys() if k.startswith("Time Series")), None)
        if not key:
            return None
        data = resp.json()[key]
        rows = []
        for ts, values in data.items():
            parsed = _parse_timestamp(ts)
            if not parsed:
                continue
            rows.append((parsed, float(values.get("4. close", 0.0))))
        if not rows:
            return None
        rows.sort(key=lambda x: x[0])
        return pd.DataFrame({"close": [v for _, v in rows]}, index=[t for t, _ in rows])
    except Exception:
        return None


def _finnhub_bars(symbol: str, resolution: str, count: int) -> Optional[pd.DataFrame]:
    api_key = os.getenv("FINNHUB_API_KEY") or getattr(ENV, "FINNHUB_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"{FINNHUB_URL}/stock/candle",
            params={
                "symbol": symbol,
                "resolution": resolution,
                "count": count,
                "token": api_key,
            },
            timeout=ENV.HTTP_TIMEOUT,
        )
        data = resp.json() if resp.status_code == 200 else {}
        if data.get("s") != "ok":
            return None
        timestamps = [datetime.fromtimestamp(ts, tz=timezone.utc) for ts in data.get("t", [])]
        closes = data.get("c", [])
        if not timestamps or not closes:
            return None
        return pd.DataFrame({"close": closes}, index=timestamps)
    except Exception:
        return None


def _twelvedata_bars(symbol: str, interval: str, outputsize: int) -> Optional[pd.DataFrame]:
    api_key = os.getenv("TWELVEDATA_API_KEY") or getattr(ENV, "TWELVEDATA_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"{TWELVEDATA_URL}/time_series",
            params={
                "symbol": symbol,
                "interval": interval,
                "outputsize": outputsize,
                "apikey": api_key,
            },
            timeout=ENV.HTTP_TIMEOUT,
        )
        data = resp.json() if resp.status_code == 200 else {}
        values = data.get("values", [])
        if not values:
            return None
        rows = []
        for item in values:
            parsed = _parse_timestamp(item.get("datetime"))
            if not parsed:
                continue
            rows.append((parsed, float(item.get("close", 0.0))))
        rows.sort(key=lambda x: x[0])
        return pd.DataFrame({"close": [v for _, v in rows]}, index=[t for t, _ in rows])
    except Exception:
        return None


def _yahoo_bars(symbol: str, interval: str, period: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(interval=interval, period=period)
        if hist.empty:
            return None
        return pd.DataFrame({"close": hist["Close"]}).sort_index()
    except Exception:
        return None


def _alpaca_bars(symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
    headers = _alpaca_headers()
    if not headers:
        return None
    base_url = ENV.ALPACA_DATA_BASE_URL.rstrip("/")
    try:
        resp = requests.get(
            f"{base_url}/stocks/{symbol}/bars",
            params={"timeframe": timeframe, "limit": limit},
            headers=headers,
            timeout=ENV.HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        payload = resp.json().get("bars") or []
        rows = []
        for bar in payload:
            ts = _parse_timestamp(bar.get("t")) or datetime.now(timezone.utc)
            rows.append((ts, float(bar.get("c", 0.0))))
        if not rows:
            return None
        rows.sort(key=lambda x: x[0])
        return pd.DataFrame({"close": [v for _, v in rows]}, index=[t for t, _ in rows])
    except Exception:
        return None


def _alpaca_headers() -> Optional[Dict[str, str]]:
    key = ENV.ALPACA_API_KEY
    secret = ENV.ALPACA_API_SECRET
    if not key or not secret:
        return None
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def get_intraday_bars(symbol: str, *, timeframe: str = "1H") -> pd.DataFrame:
    symbol = _clean_symbol(symbol)
    if not symbol:
        return pd.DataFrame(columns=["close"])
    timeframe = timeframe or "1H"
    interval_mapping = {
        "1H": ("60min", "60", "1h"),
        "15m": ("15min", "15", "15m"),
        "5m": ("5min", "5", "5m"),
    }
    alpha_interval, finnhub_interval, twelve_interval = interval_mapping.get(timeframe, ("60min", "60", "1h"))
    limit = 200 if timeframe == "5m" else 120

    providers = [
        lambda: _alpha_bars(symbol, alpha_interval),
        lambda: _finnhub_bars(symbol, finnhub_interval, limit),
        lambda: _twelvedata_bars(symbol, twelve_interval, limit),
        lambda: _yahoo_bars(symbol, interval=timeframe.lower(), period="5d" if timeframe != "1H" else "1mo"),
        lambda: _alpaca_bars(symbol, timeframe.upper(), limit),
    ]

    for fetch in providers:
        df = fetch()
        if df is not None and not df.empty:
            return df.sort_index()
    return pd.DataFrame(columns=["close"])
