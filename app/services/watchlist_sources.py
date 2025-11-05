from __future__ import annotations

import os
from typing import Iterable, List, Optional

import requests

from app.utils import env as ENV

ALPHAVANTAGE_ENDPOINT = "https://www.alphavantage.co/query"
FINNHUB_ENDPOINT = "https://finnhub.io/api/v1"
TWELVEDATA_ENDPOINT = "https://api.twelvedata.com"


def _normalize(symbols: Iterable[str]) -> List[str]:
    uniq = []
    seen = set()
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        uniq.append(sym)
    return uniq


def fetch_alpha_vantage_symbols(*, scanner: Optional[str] = None, limit: int = 50) -> List[str]:
    api_key = getattr(ENV, "ALPHAVANTAGE_API_KEY", "")
    if not api_key:
        return []
    params = {
        "function": "LISTING_STATUS",
        "state": "active",
        "apikey": api_key,
    }
    try:
        resp = requests.get(ALPHAVANTAGE_ENDPOINT, params=params, timeout=ENV.HTTP_TIMEOUT)
        if resp.status_code != 200:
            return []
        lines = resp.text.splitlines()[1:limit + 1]
        symbols = [line.split(",")[0] for line in lines if line]
        return _normalize(symbols[:limit])
    except Exception:
        return []


def fetch_finnhub_symbols(*, scanner: Optional[str] = None, limit: int = 50) -> List[str]:
    api_key = os.getenv("FINNHUB_API_KEY") or getattr(ENV, "FINNHUB_API_KEY", "")
    if not api_key:
        return []
    params = {"exchange": "US", "token": api_key}
    try:
        resp = requests.get(f"{FINNHUB_ENDPOINT}/stock/symbol", params=params, timeout=ENV.HTTP_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        symbols = [item.get("symbol", "") for item in data if item.get("type") == "Common Stock"]
        return _normalize(symbols[:limit])
    except Exception:
        return []


def fetch_twelvedata_symbols(*, scanner: Optional[str] = None, limit: int = 50) -> List[str]:
    api_key = os.getenv("TWELVEDATA_API_KEY") or getattr(ENV, "TWELVEDATA_API_KEY", "")
    if not api_key:
        return []
    params = {"source": "docs", "apikey": api_key}
    try:
        resp = requests.get(f"{TWELVEDATA_ENDPOINT}/stocks", params=params, timeout=ENV.HTTP_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", [])
        symbols = [item.get("symbol", "") for item in data if item.get("currency") == "USD"]
        return _normalize(symbols[:limit])
    except Exception:
        return []
