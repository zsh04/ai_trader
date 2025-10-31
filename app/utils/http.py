from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional, Tuple

import requests

from app.utils import env as ENV

log = logging.getLogger(__name__)


def _ensure_ua(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Ensures that a User-Agent header is present in a dictionary of headers.

    Args:
        headers (Optional[Dict[str, str]]): A dictionary of headers.

    Returns:
        Dict[str, str]: A dictionary of headers with a User-Agent header.
    """
    merged = {"User-Agent": ENV.HTTP_USER_AGENT}
    if headers:
        merged.update(headers)
    return merged


def alpaca_headers() -> Dict[str, str]:
    """
    Returns a dictionary of headers for Alpaca API requests.

    Returns:
        Dict[str, str]: A dictionary of headers.
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
    """
    Merges a dictionary of headers with the default Alpaca headers.

    Args:
        headers (Optional[Dict[str, str]]): A dictionary of headers.

    Returns:
        Dict[str, str]: A merged dictionary of headers.
    """
    merged = alpaca_headers()
    if headers:
        merged.update(headers)
    return merged


def _compute_sleep(attempt: int, backoff: float, retry_after: Optional[str]) -> float:
    """
    Computes the sleep time for a retry.

    Args:
        attempt (int): The current retry attempt.
        backoff (float): The backoff factor.
        retry_after (Optional[str]): The value of the Retry-After header.

    Returns:
        float: The sleep time in seconds.
    """
    if retry_after:
        try:
            val = float(retry_after)
            if val > 0:
                return val
        except Exception:
            pass
    jitter = random.uniform(0.85, 1.15)
    return max(0.1, backoff * (attempt + 1) * jitter)


def _log_http_event(
    *,
    level: int,
    method: str,
    url: str,
    status: int,
    attempt: int,
    retries: int,
    start_time: float,
    note: str = "",
) -> None:
    """
    Logs an HTTP event.

    Args:
        level (int): The logging level.
        method (str): The HTTP method.
        url (str): The URL.
        status (int): The HTTP status code.
        attempt (int): The current retry attempt.
        retries (int): The total number of retries.
        start_time (float): The start time of the request.
        note (str): An optional note.
    """
    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 1)
    log.log(
        level,
        "[http] method=%s url=%s status=%s latency_ms=%.1f attempt=%s/%s %s",
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
    """
    Makes an HTTP request and returns the JSON response.

    Args:
        method (str): The HTTP method.
        url (str): The URL to request.
        params (Optional[Dict[str, Any]]): The request parameters.
        headers (Optional[Dict[str, str]]): The request headers.
        json (Optional[Dict[str, Any]]): The request JSON body.
        data (Any): The request data.
        timeout (Optional[int]): The request timeout.
        retries (Optional[int]): The number of retries.
        backoff (Optional[float]): The backoff factor.
        session (Optional[requests.Session]): The request session.

    Returns:
        Tuple[int, Dict[str, Any]]: A tuple of (status_code, response_data).
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

            if 200 <= resp.status_code < 300:
                _log_http_event(
                    level=logging.INFO,
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
                    log.exception("JSON decode failed for %s", url)
                    return resp.status_code, {}

            retryable = resp.status_code in {408, 429, 500, 502, 503, 504}
            if retryable and attempt < retries:
                sleep_s = _compute_sleep(
                    attempt, backoff, resp.headers.get("Retry-After")
                )
                _log_http_event(
                    level=logging.WARNING,
                    method=method,
                    url=url,
                    status=resp.status_code,
                    attempt=attempt,
                    retries=retries,
                    start_time=start_time,
                    note="retry",
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

            _log_http_event(
                level=logging.WARNING,
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
                body = (resp.text or "")[:400]
                log.debug("Non-JSON response for %s: %s", url, body)
                return resp.status_code, {}

        except requests.RequestException as e:
            last_exc = e
            _log_http_event(
                level=logging.WARNING,
                method=method,
                url=url,
                status=599,
                attempt=attempt,
                retries=retries,
                start_time=start_time,
                note=f"error={e}",
            )
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


def http_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    *,
    timeout: Optional[int] = None,
    retries: Optional[int] = None,
    backoff: Optional[float] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Makes an HTTP GET request and returns the JSON response.

    Args:
        url (str): The URL to request.
        params (Optional[Dict[str, Any]]): The request parameters.
        headers (Optional[Dict[str, str]]): The request headers.
        timeout (Optional[int]): The request timeout.
        retries (Optional[int]): The number of retries.
        backoff (Optional[float]): The backoff factor.

    Returns:
        Tuple[int, Dict[str, Any]]: A tuple of (status_code, response_data).
    """
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
    """
    Makes an HTTP POST request with a JSON body and returns the JSON response.

    Args:
        url (str): The URL to request.
        json_body (Optional[Dict[str, Any]]): The request JSON body.
        headers (Optional[Dict[str, str]]): The request headers.
        timeout (Optional[int]): The request timeout.
        retries (Optional[int]): The number of retries.
        backoff (Optional[float]): The backoff factor.

    Returns:
        Tuple[int, Dict[str, Any]]: A tuple of (status_code, response_data).
    """
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
