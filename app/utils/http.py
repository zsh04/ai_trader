from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional, Tuple

import requests

from app.utils import env as ENV

log = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Header helpers
# ------------------------------------------------------------------------------


def _ensure_ua(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged = {"User-Agent": ENV.HTTP_USER_AGENT}
    if headers:
        merged.update(headers)
    return merged


def alpaca_headers() -> Dict[str, str]:
    """Standard Alpaca auth + JSON + UA headers.
    Returns minimal JSON headers if keys are missing so callers can handle 401s.
    """
    base = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": ENV.HTTP_USER_AGENT,
    }
    if ENV.ALPACA_API_KEY and ENV.ALPACA_API_SECRET:
        base["APCA-API-KEY-ID"] = ENV.ALPACA_API_KEY
        base["APCA-API-SECRET-KEY"] = ENV.ALPACA_API_SECRET
    return base


def with_alpaca(headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Merge caller headers with alpaca auth + UA."""
    merged = alpaca_headers()
    if headers:
        merged.update(headers)
    return merged


# ------------------------------------------------------------------------------
# Core HTTP (JSON) with retries and jittered backoff
# ------------------------------------------------------------------------------


def _compute_sleep(attempt: int, backoff: float, retry_after: Optional[str]) -> float:
    # Respect Retry-After if present and valid
    if retry_after:
        try:
            val = float(retry_after)
            if val > 0:
                return val
        except Exception:
            pass
    # Jittered backoff: base * (attempt+1) * (0.85..1.15)
    jitter = random.uniform(0.85, 1.15)
    return max(0.1, backoff * (attempt + 1) * jitter)


def request_json(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    json: Optional[Dict[str, Any]] = None,
    data: Any = None,
    timeout: Optional[int] = None,
    retries: Optional[int] = None,
    backoff: Optional[float] = None,
    session: Optional[requests.Session] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Make an HTTP request expecting JSON. Returns (status_code, json_dict).

    - Retries on 408/429/5xx and network errors up to `retries` times with jittered backoff.
    - Respects `Retry-After` header when present.
    - On non-JSON responses, returns empty dict.
    - On repeated network failure, returns (599, {}).
    """
    timeout = timeout if timeout is not None else ENV.HTTP_TIMEOUT_SECS
    retries = (
        retries
        if retries is not None
        else getattr(ENV, "HTTP_RETRIES", ENV.HTTP_RETRY_ATTEMPTS)
    )
    backoff = backoff if backoff is not None else ENV.HTTP_RETRY_BACKOFF_SEC

    merged = _ensure_ua(headers)

    client = session or requests
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            resp = client.request(
                method=method.upper(),
                url=url,
                params=params or {},
                headers=merged,
                json=json,
                data=data,
                timeout=timeout,
            )

            # Success path
            if 200 <= resp.status_code < 300:
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    log.exception("JSON decode failed for %s", url)
                    return resp.status_code, {}

            # Retryable?
            retryable = resp.status_code in {408, 429, 500, 502, 503, 504}
            if retryable and attempt < retries:
                sleep_s = _compute_sleep(
                    attempt, backoff, resp.headers.get("Retry-After")
                )
                log.warning(
                    "HTTP %s %s -> %s — retry %s/%s in %.2fs",
                    method.upper(),
                    url,
                    resp.status_code,
                    attempt + 1,
                    retries,
                    sleep_s,
                )
                time.sleep(sleep_s)
                continue

            # Non-retriable or exhausted
            try:
                return resp.status_code, resp.json()
            except Exception:
                # Truncate body for logging
                body = (resp.text or "")[:400]
                log.debug("Non-JSON response for %s: %s", url, body)
                return resp.status_code, {}

        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                sleep_s = _compute_sleep(attempt, backoff, None)
                log.warning(
                    "HTTP %s %s error — retry %s/%s in %.2fs: %s",
                    method.upper(),
                    url,
                    attempt + 1,
                    retries,
                    sleep_s,
                    e,
                )
                time.sleep(sleep_s)
                continue
            break

    if last_exc:
        log.error("HTTP %s %s failed after retries: %s", method.upper(), url, last_exc)
    return 599, {}


# ------------------------------------------------------------------------------
# Convenience wrappers (backward compatible signatures)
# ------------------------------------------------------------------------------


def http_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    *,
    timeout: Optional[int] = None,
    retries: Optional[int] = None,
    backoff: Optional[float] = None,
) -> Tuple[int, Dict[str, Any]]:
    return request_json(
        "GET",
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        retries=retries,
        backoff=backoff,
    )


def http_post_json(
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    *,
    timeout: Optional[int] = None,
    retries: Optional[int] = None,
    backoff: Optional[float] = None,
) -> Tuple[int, Dict[str, Any]]:
    # Ensure JSON content-type by default
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    return request_json(
        "POST",
        url,
        headers=h,
        json=json_body or {},
        timeout=timeout,
        retries=retries,
        backoff=backoff,
    )
