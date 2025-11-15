from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

from ui.settings.config import AppSettings
from ui.utils.request_id import generate_request_id
from ui.utils.telemetry import child_span

logger = logging.getLogger(__name__)


class ServiceError(RuntimeError):
    category: str

    def __init__(self, message: str, *, category: str) -> None:
        super().__init__(message)
        self.category = category


class HttpClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": f"ai-trader-ui/{settings.app_version}"}
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        ui_action: str = "",
        request_id: Optional[str] = None,
    ) -> Any:
        url = f"{self.settings.api_base_url}{path}"
        retries = 3
        backoff = 0.5
        req_id = request_id or generate_request_id()
        headers = {
            "x-request-id": req_id,
            "x-ui-action": ui_action or path,
        }
        for attempt in range(1, retries + 1):
            try:
                with child_span(
                    f"ui.http.{method.lower()}",
                    {
                        "http.method": method,
                        "api.path": path,
                        "ui_action": ui_action or "",
                    },
                ):
                    start = time.perf_counter()
                    response = self.session.request(
                        method,
                        url,
                        params=params,
                        json=json,
                        timeout=(5, 15),
                        headers=headers,
                    )
                    latency_ms = (time.perf_counter() - start) * 1000
                    if response.status_code >= 400:
                        self._handle_error(response, latency_ms, ui_action)
                    logger.info(
                        "api success",
                        extra={
                            "ui_action": ui_action,
                            "latency_ms": latency_ms,
                            "request_id": req_id,
                        },
                    )
                    return response.json() if response.content else None
            except ServiceError:
                raise
            except requests.Timeout as exc:
                logger.warning(
                    "api timeout",
                    extra={
                        "attempt": attempt,
                        "ui_action": ui_action,
                        "request_id": req_id,
                    },
                )
                if attempt == retries:
                    raise ServiceError("network timeout", category="network") from exc
            except requests.RequestException as exc:
                logger.warning(
                    "api error",
                    extra={
                        "attempt": attempt,
                        "ui_action": ui_action,
                        "request_id": req_id,
                    },
                )
                if attempt == retries:
                    raise ServiceError("network failure", category="network") from exc
            time.sleep(backoff)
            backoff = min(backoff * 2, 2.0)

    def _handle_error(
        self, response: requests.Response, latency_ms: float, action: str
    ) -> None:
        status = response.status_code
        category = "server"
        if status == 400:
            category = "user"
        elif status == 404:
            category = "not_found"
        elif status >= 500:
            category = "server"
        message = f"API {status}: {response.text}"[:400]
        logger.error(
            "api failure",
            extra={
                "status": status,
                "ui_action": action,
                "latency_ms": latency_ms,
            },
        )
        raise ServiceError(message, category=category)
