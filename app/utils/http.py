from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional, Tuple

import requests
from loguru import logger

from app.utils import env as ENV

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


def compute_backoff_delay(
    attempt: int, backoff: float, retry_after: Optional[str]
) -> float:
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


def _log_http_event(
    *,
    level: str,
    method: str,
    url: str,
    status: int,
    attempt: int,
    retries: int,
    start_time: float,
    note: str = "",
) -> None:
    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 1)
    logger.log(
        level,
        "[http] method={} url={} status={} latency_ms={:.1f} attempt={}/{} {}",
        method.upper(),
        url,
        status,
        latency_ms,
        attempt + 1,
        retries + 1,
        note,
    )


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
    timeout = timeout if timeout is not None else ENV.HTTP_TIMEOUT
    retries = retries if retries is not None else ENV.HTTP_RETRIES
    backoff = backoff if backoff is not None else ENV.HTTP_BACKOFF

    merged = _ensure_ua(headers)

    client = session or requests
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        start_time = time.perf_counter()
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
                _log_http_event(
                    level="INFO",
                    method=method,
                    url=url,
                    status=resp.status_code,
                    attempt=attempt,
                    retries=retries,
                    start_time=start_time,
                    note="ok",
                )
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    logger.exception("JSON decode failed for {}", url)
                    return resp.status_code, {}

            # Retryable?
            retryable = resp.status_code in {408, 429, 500, 502, 503, 504}
            if retryable and attempt < retries:
                sleep_s = compute_backoff_delay(
                    attempt, backoff, resp.headers.get("Retry-After")
                )
                _log_http_event(
                    level="WARNING",
                    method=method,
                    url=url,
                    status=resp.status_code,
                    attempt=attempt,
                    retries=retries,
                    start_time=start_time,
                    note="retry",
                )
                logger.warning(
                    "HTTP {} {} -> {} — retry {}/{} in {:.2f}s",
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
            _log_http_event(
                level="WARNING",
                method=method,
                url=url,
                status=resp.status_code,
                attempt=attempt,
                retries=retries,
                start_time=start_time,
                note="non-2xx",
            )
            try:
                return resp.status_code, resp.json()
            except Exception:
                # Truncate body for logging
                body = (resp.text or "")[:400]
                logger.debug("Non-JSON response for {}: {}", url, body)
                return resp.status_code, {}

        except requests.RequestException as e:
            last_exc = e
            _log_http_event(
                level="WARNING",
                method=method,
                url=url,
                status=599,
                attempt=attempt,
                retries=retries,
                start_time=start_time,
                note=f"error={e}",
            )
            if attempt < retries:
                sleep_s = compute_backoff_delay(attempt, backoff, None)
                logger.warning(
                    "HTTP {} {} error — retry {}/{} in {:.2f}s: {}",
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
        logger.error(
            "HTTP {} {} failed after retries: {}", method.upper(), url, last_exc
        )
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
