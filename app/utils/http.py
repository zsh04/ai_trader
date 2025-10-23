from __future__ import annotations
import logging, time, requests
from typing import Any, Dict, Optional, Tuple
from app.utils.env import (
    ALPACA_API_KEY, ALPACA_API_SECRET,
    HTTP_TIMEOUT_SECS, HTTP_RETRIES, HTTP_RETRY_BACKOFF
)

log = logging.getLogger(__name__)

def alpaca_headers() -> Dict[str, str]:
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        # Do not raise here; allow caller to handle auth failures gracefully
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    return {
        "Apca-Api-Key-Id": ALPACA_API_KEY,
        "Apca-Api-Secret-Key": ALPACA_API_SECRET,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def http_get(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[int, Dict[str, Any]]:
    last_exc = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers or {}, params=params or {}, timeout=HTTP_TIMEOUT_SECS)
            if 200 <= resp.status_code < 300:
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    log.exception("JSON decode failed for %s", url)
                    return resp.status_code, {}
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < HTTP_RETRIES:
                time.sleep(HTTP_RETRY_BACKOFF * (attempt + 1))
                continue
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
        log.error("GET %s failed: %s", url, last_exc)
    return 599, {}