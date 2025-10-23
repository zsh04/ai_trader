# app/data/data_client.py
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
import requests

try:
    # Optional: if you have a settings object, use it
    from app.config import settings  # type: ignore
except Exception:
    settings = None  # fallback to os.environ

log = logging.getLogger(__name__)

# ------------------------------
# Config & Helpers
# ------------------------------

def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    if settings and hasattr(settings, key):
        return getattr(settings, key)
    return os.environ.get(key, default)

ALPACA_API_KEY: str = _env("ALPACA_API_KEY", "") or ""
ALPACA_API_SECRET: str = _env("ALPACA_API_SECRET", "") or ""
# Trading base URL typically paper/live (orders). Data uses a different host.
ALPACA_BASE_URL: str = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets") or "https://paper-api.alpaca.markets"
# Data v2 base URL (same for paper/live accounts)
ALPACA_DATA_BASE_URL: str = _env("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets/v2") or "https://data.alpaca.markets/v2"
# Feed for paper is usually "iex"; if you have SIP, set ALPACA_FEED=sip

ALPACA_FEED: str = _env("ALPACA_FEED", "iex") or "iex"

# Yahoo/Other price providers config
PRICE_PROVIDERS: List[str] = [s.strip() for s in (_env("PRICE_PROVIDERS", "alpaca,yahoo") or "").split(",") if s.strip()]
YF_TIMEOUT_SECS = float(_env("YF_TIMEOUT_SECS", "6") or 6)
YF_ENABLED = any(p.lower() == "yahoo" for p in PRICE_PROVIDERS)

HTTP_TIMEOUT_SECS = float(_env("HTTP_TIMEOUT_SECS", "10") or 10)
HTTP_RETRIES = int(_env("HTTP_RETRIES", "2") or 2)
HTTP_RETRY_BACKOFF = float(_env("HTTP_RETRY_BACKOFF", "0.5") or 0.5)

def _headers() -> Dict[str, str]:
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        raise RuntimeError("Missing ALPACA_API_KEY / ALPACA_API_SECRET")
    return {
        "Apca-Api-Key-Id": ALPACA_API_KEY,
        "Apca-Api-Secret-Key": ALPACA_API_SECRET,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _http_get(url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
    last_exc: Optional[Exception] = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_headers(), params=params or {}, timeout=HTTP_TIMEOUT_SECS)
            if resp.status_code >= 200 and resp.status_code < 300:
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    log.exception("Failed to decode JSON from %s", url)
                    return resp.status_code, {}
            # retry on 5xx and 429
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < HTTP_RETRIES:
                time.sleep(HTTP_RETRY_BACKOFF * (attempt + 1))
                continue
            # non-retryable
            log.warning("HTTP %s from %s params=%s body=%s", resp.status_code, url, params, resp.text[:500])
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, {}
        except requests.RequestException as e:
            last_exc = e
            if attempt < HTTP_RETRIES:
                time.sleep(HTTP_RETRY_BACKOFF * (attempt + 1))
                continue
    if last_exc:
        log.error("GET %s failed after retries: %s", url, last_exc)
    return 599, {}

# ------------------------------
# Helper: normalize bars payload
# ------------------------------

def _normalize_bars_to_map(bars_obj: Any, symbols: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize Alpaca v2 bars payload into {SYM: [bar,...]} regardless of shape.
    Accepts either a list of bar dicts (with 'S' or 'T' symbol field) or
    a dict mapping symbol->list[bar]. Missing/unknown shapes return an empty map
    seeded with provided symbols.
    """
    out: Dict[str, List[Dict[str, Any]]] = {s: [] for s in symbols}
    if isinstance(bars_obj, list):
        for b in bars_obj:
            if not isinstance(b, dict):
                continue
            sym = (b.get("S") or b.get("T") or "").upper()
            if not sym:
                continue
            out.setdefault(sym, []).append(b)
    elif isinstance(bars_obj, dict):
        for k, v in bars_obj.items():
            sym = (k or "").upper()
            if not sym:
                continue
            seq = v if isinstance(v, list) else []
            out.setdefault(sym, []).extend([x for x in seq if isinstance(x, dict)])
    return out

# ------------------------------
# Yahoo Finance fallback (lazy import)
# ------------------------------

def _yf_imports():
    import importlib
    try:
        yf = importlib.import_module("yfinance")
        return yf
    except Exception as e:
        log.debug("yfinance not available: %s", e)
        return None


def yf_latest_close(symbols: List[str]) -> Dict[str, float]:
    """Return last regular-market close per symbol using yfinance (best-effort)."""
    if not YF_ENABLED or not symbols:
        return {}
    yf = _yf_imports()
    if yf is None:
        return {}
    out: Dict[str, float] = {}
    for sym in symbols:
        try:
            tk = yf.Ticker(sym)
            close_val = None
            # try fast_info first
            fi = getattr(tk, "fast_info", None)
            if isinstance(fi, dict):
                close_val = fi.get("previous_close") or fi.get("last_close") or fi.get("last_price")
            if close_val is None:
                hist = tk.history(period="5d", interval="1d", prepost=True)
                if hist is not None and len(hist) > 0:
                    close_val = float(hist["Close"].iloc[-1])
            if close_val is not None and float(close_val) > 0:
                out[sym.upper()] = float(close_val)
        except Exception as e:
            log.debug("yf_latest_close error %s: %s", sym, e)
            continue
    return out


def yf_intraday_last(symbols: List[str]) -> Dict[str, float]:
    """Return recent intraday last (1m) using yfinance (best-effort, may lag)."""
    if not YF_ENABLED or not symbols:
        return {}
    yf = _yf_imports()
    if yf is None:
        return {}
    out: Dict[str, float] = {}
    for sym in symbols:
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="1d", interval="1m", prepost=True)
            if hist is not None and len(hist) > 0:
                out[sym.upper()] = float(hist["Close"].iloc[-1])
        except Exception as e:
            log.debug("yf_intraday_last error %s: %s", sym, e)
            continue
    return out


# ------------------------------
# Yahoo helpers: volume and latest day bar
# ------------------------------

def yf_latest_volume(symbols: List[str]) -> Dict[str, int]:
    """Return last daily volume per symbol using yfinance (best-effort)."""
    if not YF_ENABLED or not symbols:
        return {}
    yf = _yf_imports()
    if yf is None:
        return {}
    out: Dict[str, int] = {}
    for sym in symbols:
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="5d", interval="1d", prepost=True)
            if hist is not None and len(hist) > 0 and "Volume" in hist.columns:
                vol = int(hist["Volume"].iloc[-1])
                if vol > 0:
                    out[sym.upper()] = vol
        except Exception as e:
            log.debug("yf_latest_volume error %s: %s", sym, e)
            continue
    return out


def get_latest_day_bar_map(symbols: List[str], feed: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Fetch the most recent 1Day bar for each symbol and return a map {SYM: bar}.
    Uses get_daily_bars(limit=1) under the hood.
    """
    if not symbols:
        return {}
    bars_map = get_daily_bars(symbols, limit=1, feed=feed)
    out: Dict[str, Dict[str, Any]] = {}
    for sym in symbols:
        seq = bars_map.get(sym.upper(), [])
        if seq:
            b = seq[-1]
            if isinstance(b, dict):
                out[sym.upper()] = b
    return out

# ------------------------------
# Data API calls
# ------------------------------

def get_snapshots_batch(symbols: List[str], feed: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    GET /v2/stocks/snapshots?symbols=SPY,AAPL&feed=iex|sip
    Returns a dict: { "AAPL": {snapshot...}, "SPY": {...} }
    """
    feed = feed or ALPACA_FEED
    syms = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return {}
    url = f"{ALPACA_DATA_BASE_URL}/stocks/snapshots"
    status, data = _http_get(url, {"symbols": ",".join(syms), "feed": feed})
    log.info("alpaca snapshots status=%s symbols=%s feed=%s", status, ",".join(syms), feed)
    if status != 200:
        log.warning("alpaca snapshots non-200: status=%s body=%s", status, str(data)[:500])
        return {}
    # Response shape: {"snapshots": {"AAPL": {...}, "SPY": {...}}}
    snaps = data.get("snapshots") or {}
    if not snaps:
        log.warning("alpaca snapshots EMPTY for symbols=%s feed=%s", ",".join(syms), feed)
    # Normalize keys to upper
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in snaps.items():
        out[(k or "").upper()] = v or {}
    return out

def get_minutes_bars(symbols: List[str], timeframe: str = "1Min", limit: int = 1, feed: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    GET /v2/stocks/bars?symbols=AAPL,SPY&timeframe=1Min&limit=1&feed=iex
    Returns dict: { "AAPL": [ { "t": "...", "o":..., "h":..., "l":..., "c":..., "v":... } ], ... }
    """
    feed = feed or ALPACA_FEED
    syms = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return {}
    url = f"{ALPACA_DATA_BASE_URL}/stocks/bars"
    params = {"symbols": ",".join(syms), "timeframe": timeframe, "limit": int(limit), "feed": feed}
    status, data = _http_get(url, params)
    if status != 200:
        return {s: [] for s in syms}
    bars_obj = data.get("bars")
    return _normalize_bars_to_map(bars_obj, syms)

# ------------------------------
# Helper: get_latest_closes
# ------------------------------

def get_latest_closes(symbols: List[str], feed: Optional[str] = None) -> Dict[str, float]:
    """
    Batch fetch last daily close for symbols via /v2/stocks/bars (1Day, limit=1).
    Returns: { "AAPL": 187.12, "SPY": 428.50, ... }
    """
    feed = feed or ALPACA_FEED
    syms = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return {}
    url = f"{ALPACA_DATA_BASE_URL}/stocks/bars"
    params = {
        "symbols": ",".join(syms),
        "timeframe": "1Day",
        "limit": 1,
        "feed": feed,
    }
    status, data = _http_get(url, params)
    if status != 200:
        log.warning("get_latest_closes non-200: status=%s body=%s", status, str(data)[:500])
        return {}
    bars_map = _normalize_bars_to_map(data.get("bars"), syms)
    out: Dict[str, float] = {}
    for sym in syms:
        seq = bars_map.get(sym, [])
        if not seq:
            continue
        try:
            c = float(seq[-1].get("c", 0) or 0)
            if c > 0:
                out[sym] = c
        except Exception:
            continue
    if not out:
        log.warning("get_latest_closes returned empty for symbols=%s feed=%s", ",".join(syms), feed)
    return out

# ------------------------------
# Snapshot parsing & fallbacks
# ------------------------------

def _midquote(snap: Dict[str, Any]) -> float:
    q = (snap or {}).get("latestQuote") or {}
    bp = q.get("bp"); ap = q.get("ap")
    try:
        if bp is not None and ap is not None and float(bp) > 0 and float(ap) > 0:
            return float((float(bp) + float(ap)) / 2.0)
    except Exception:
        pass
    return 0.0

def _latest_1m_close(symbol: str) -> float:
    try:
        m = get_minutes_bars([symbol], timeframe="1Min", limit=1)
        arr = m.get(symbol.upper(), [])
        if arr:
            c = arr[-1].get("c")
            if c is not None:
                return float(c)
    except Exception as e:
        log.debug("latest_1m_close error for %s: %s", symbol, e)
    return 0.0

def latest_price_from_snapshot(snap: Dict[str, Any], symbol: str) -> float:
    """
    Fallback order:
      1) latestTrade.p
      2) midquote (bp/ap)
      3) last 1m bar close
      4) dailyBar.c
      5) prevDailyBar.c
    """
    try:
        lt = (snap or {}).get("latestTrade") or {}
        p = lt.get("p")
        if p is not None and float(p) > 0:
            return float(p)
    except Exception:
        pass

    mid = _midquote(snap)
    if mid > 0:
        return mid

    last1 = _latest_1m_close(symbol)
    if last1 > 0:
        return last1

    try:
        dbar = (snap or {}).get("dailyBar") or {}
        if dbar.get("c") is not None and float(dbar.get("c") or 0) > 0:
            return float(dbar["c"])
    except Exception:
        pass

    try:
        pbar = (snap or {}).get("prevDailyBar") or {}
        if pbar.get("c") is not None and float(pbar.get("c") or 0) > 0:
            return float(pbar["c"])
    except Exception:
        pass

    return 0.0

def snapshot_to_ohlcv(snap: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prefer today's dailyBar; if empty/zero (premarket/after-hours), fall back to prevDailyBar.
    """
    dbar = (snap or {}).get("dailyBar") or {}
    pbar = (snap or {}).get("prevDailyBar") or {}
    pick = dbar if (dbar.get("c") not in (None, 0, 0.0)) else pbar
    def _f(x: Any, kind: str) -> float:
        try:
            return float(x or 0.0)
        except Exception:
            log.debug("snapshot_to_ohlcv parse error kind=%s x=%s", kind, x)
            return 0.0
    return {
        "o": _f((pick or {}).get("o"), "o"),
        "h": _f((pick or {}).get("h"), "h"),
        "l": _f((pick or {}).get("l"), "l"),
        "c": _f((pick or {}).get("c"), "c"),
        "v": int((pick or {}).get("v") or 0),
    }

# ------------------------------
# Public batch API used by endpoints
# ------------------------------

def batch_latest_ohlcv(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Returns:
      {
        "AAPL": {
          "last": 187.34,
          "price_source": "trade|midquote|1m|daily|prev_daily|bars_close|none",
          "ohlcv": {"o":..., "h":..., "l":..., "c":..., "v":...}
        },
        ...
      }
    """
    syms = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return {}
    snaps = get_snapshots_batch(syms)
    out: Dict[str, Dict[str, Any]] = {}

    needs_bars_close: List[str] = []

    # First pass: fill from snapshots and per-symbol fallbacks
    for sym in syms:
        snap = snaps.get(sym) or {}
        last, source = latest_price_with_source(snap, sym)
        ohlcv = snapshot_to_ohlcv(snap)

        if last <= 0:
            needs_bars_close.append(sym)

        out[sym] = {
            "last": last,
            "price_source": source,
            "ohlcv": ohlcv,
        }

    # Second pass: hydrate from latest 1Day bar (price + volume) in one shot
    needs_vol_from_bar: List[str] = [sym for sym, d in out.items() if int((d.get("ohlcv") or {}).get("v", 0)) <= 0]
    union_syms = sorted(set(needs_bars_close + needs_vol_from_bar))
    if union_syms:
        latest_bar_map = get_latest_day_bar_map(union_syms)
        for sym in union_syms:
            b = latest_bar_map.get(sym)
            if not b:
                continue
            # fill price if still zero
            if out[sym]["last"] <= 0:
                try:
                    cval = float(b.get("c") or 0)
                    if cval > 0:
                        out[sym]["last"] = cval
                        out[sym]["price_source"] = "bars_close"
                except Exception:
                    pass
            # hydrate OHLCV fields if missing/zero (esp. volume)
            ohlcv = out[sym].get("ohlcv") or {}
            changed = False
            try:
                if float(ohlcv.get("o") or 0) <= 0 and b.get("o") is not None:
                    ohlcv["o"] = float(b.get("o") or 0)
                    changed = True
                if float(ohlcv.get("h") or 0) <= 0 and b.get("h") is not None:
                    ohlcv["h"] = float(b.get("h") or 0)
                    changed = True
                if float(ohlcv.get("l") or 0) <= 0 and b.get("l") is not None:
                    ohlcv["l"] = float(b.get("l") or 0)
                    changed = True
                if float(ohlcv.get("c") or 0) <= 0 and b.get("c") is not None:
                    ohlcv["c"] = float(b.get("c") or 0)
                    changed = True
                if int(ohlcv.get("v") or 0) <= 0 and b.get("v") is not None:
                    try:
                        ohlcv["v"] = int(b.get("v") or 0)
                        changed = True
                    except Exception:
                        pass
            except Exception:
                pass
            if changed:
                out[sym]["ohlcv"] = ohlcv

    # Third pass: Yahoo Finance fallback for unresolved zeros (if enabled)
    unresolved = [sym for sym, d in out.items() if (d.get("last") or 0) <= 0]
    if YF_ENABLED and unresolved:
        y_intr = yf_intraday_last(unresolved)
        # symbols without intraday get close
        remaining = [s for s in unresolved if s not in y_intr]
        y_close = yf_latest_close(remaining) if remaining else {}
        for sym in unresolved:
            if sym in y_intr and y_intr[sym] > 0:
                out[sym]["last"] = y_intr[sym]
                out[sym]["price_source"] = "yahoo_1m"
            elif sym in y_close and y_close[sym] > 0:
                out[sym]["last"] = y_close[sym]
                out[sym]["price_source"] = "yahoo_close"

    # Fourth pass: Yahoo daily volume for any symbols still showing v==0
    unresolved_vol = [sym for sym, d in out.items() if int((d.get("ohlcv") or {}).get("v", 0)) <= 0]
    if YF_ENABLED and unresolved_vol:
        y_vol = yf_latest_volume(unresolved_vol)
        for sym in unresolved_vol:
            vol = y_vol.get(sym)
            if vol and vol > 0:
                ohlcv = out[sym].get("ohlcv") or {}
                ohlcv["v"] = int(vol)
                out[sym]["ohlcv"] = ohlcv

    return out

# ------------------------------
# Helper: latest_price_with_source
# ------------------------------

def latest_price_with_source(snap: Dict[str, Any], symbol: str) -> Tuple[float, str]:
    """Same logic as latest_price_from_snapshot but returns (price, source)."""
    try:
        lt = (snap or {}).get("latestTrade") or {}
        p = lt.get("p")
        if p is not None and float(p) > 0:
            return float(p), "trade"
    except Exception:
        pass

    mid = _midquote(snap)
    if mid > 0:
        return mid, "midquote"

    last1 = _latest_1m_close(symbol)
    if last1 > 0:
        return last1, "1m"

    try:
        dbar = (snap or {}).get("dailyBar") or {}
        if dbar.get("c") is not None and float(dbar.get("c") or 0) > 0:
            return float(dbar["c"]), "daily"
    except Exception:
        pass

    try:
        pbar = (snap or {}).get("prevDailyBar") or {}
        if pbar.get("c") is not None and float(pbar.get("c") or 0) > 0:
            return float(pbar["c"]), "prev_daily"
    except Exception:
        pass

    # Fallback: try to fetch last close from daily bars API
    try:
        bars = get_daily_bars([symbol], limit=1)
        if bars and symbol.upper() in bars:
            bar_list = bars[symbol.upper()]
            if bar_list and isinstance(bar_list, list):
                close_val = float(bar_list[-1].get("c", 0) or 0)
                if close_val > 0:
                    return close_val, "bars_close"
    except Exception as e:
        log.debug("latest_price_with_source: bars_close fallback failed for %s: %s", symbol, e)

    return 0.0, "none"

# ------------------------------
# Compatibility & convenience for scanners
# ------------------------------

def get_universe() -> List[str]:
    """Return default scanning universe from env or sensible defaults."""
    raw = _env("WATCHLIST_UNIVERSE")
    if raw:
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return [
        "SPY","QQQ","IWM","AAPL","MSFT","NVDA","TSLA","META","AMZN","GOOGL",
        "SHOP","NFLX","AMD","INTC","SMCI","PLTR","SOFI","MARA","RIOT","SOUN"
    ]

def get_daily_bars(symbols: List[str], limit: int = 1, feed: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Thin wrapper over /v2/stocks/bars for 1Day timeframe.
    Returns: { "AAPL": [ {t, o, h, l, c, v}, ... ], ... }
    """
    feed = feed or ALPACA_FEED
    syms = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return {}
    url = f"{ALPACA_DATA_BASE_URL}/stocks/bars"
    params = {
        "symbols": ",".join(syms),
        "timeframe": "1Day",
        "limit": int(limit),
        "feed": feed,
    }
    status, data = _http_get(url, params)
    if status != 200:
        return {s: [] for s in syms}
    bars_obj = data.get("bars")
    return _normalize_bars_to_map(bars_obj, syms)

def get_minute_bars(symbols: List[str], limit: int = 1, feed: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Alias to get_minutes_bars(timeframe='1Min') for legacy callers."""
    return get_minutes_bars(symbols, timeframe="1Min", limit=limit, feed=feed)