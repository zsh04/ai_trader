# app/adapters/market/alpaca_client.py
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.utils import env as ENV
from app.utils.http import request_json

__all__ = ["AlpacaMarketClient", "AlpacaAuthError"]

_ALLOWED_FEEDS = {"iex", "sip"}


def _normalize_symbols(symbols: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for raw in symbols or []:
        if not raw:
            continue
        sym = raw.strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        ordered.append(sym)
    return ordered


class AlpacaAuthError(RuntimeError):
    """Raised when Alpaca returns a persistent 401."""

    def __init__(self, message: str, *, fallback_to_yahoo: bool) -> None:
        super().__init__(message)
        self.fallback_to_yahoo = fallback_to_yahoo


class AlpacaMarketClient:
    """
    Lightweight Alpaca market-data adapter with explicit feed selection.

    - Respects configured IEX/SIP feed hints per-request.
    - Adds mandatory authentication headers in every call.
    - Retries **one time** on HTTP 401, then raises ``AlpacaAuthError`` and logs
      actionable guidance. When the ``ALPACA_FORCE_YAHOO_ON_AUTH_ERROR`` flag is
      enabled, the error advertises a Yahoo fallback for upstream handlers.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        default_feed: Optional[str] = None,
        timeout: Optional[int] = None,
        retries: Optional[int] = None,
        backoff: Optional[float] = None,
        force_yahoo_on_auth_error: Optional[bool] = None,
        transport=request_json,
        session=None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else ENV.ALPACA_API_KEY
        self.api_secret = (
            api_secret if api_secret is not None else ENV.ALPACA_API_SECRET
        )
        self.base_url = (base_url or ENV.ALPACA_DATA_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else ENV.HTTP_TIMEOUT
        self.retries = (
            retries if retries is not None else getattr(ENV, "HTTP_RETRIES", 2)
        )
        self.backoff = (
            backoff if backoff is not None else getattr(ENV, "HTTP_BACKOFF", 1.5)
        )
        self.default_feed = self._resolve_feed(default_feed or ENV.ALPACA_FEED)
        self.force_yahoo_on_auth_error = (
            force_yahoo_on_auth_error
            if force_yahoo_on_auth_error is not None
            else getattr(ENV, "ALPACA_FORCE_YAHOO_ON_AUTH_ERROR", False)
        )
        self._transport = transport
        self._session = session
        self.log = logger or logging.getLogger(__name__)

    # --------------------------------------------------------------------- #
    # Public API                                                            #
    # --------------------------------------------------------------------- #
    def snapshots(
        self, symbols: Sequence[str], *, feed: Optional[str] = None
    ) -> Tuple[int, Dict[str, Any]]:
        clean = _normalize_symbols(symbols)
        if not clean:
            return 200, {}
        params = {"symbols": ",".join(clean)}
        status, payload = self._request(
            "stocks/snapshots", params=params, feed=feed
        )
        snaps = (payload or {}).get("snapshots") or {}
        return status, snaps

    # --------------------------------------------------------------------- #
    # Internals                                                             #
    # --------------------------------------------------------------------- #
    def _resolve_feed(self, feed: Optional[str]) -> str:
        if not feed:
            return self.default_feed
        value = feed.strip().lower()
        if value in _ALLOWED_FEEDS:
            return value
        self.log.warning(
            "[alpaca] unknown feed=%s; defaulting to %s", feed, self.default_feed
        )
        return self.default_feed

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": ENV.HTTP_USER_AGENT,
        }
        if self.api_key:
            headers["APCA-API-KEY-ID"] = self.api_key
        if self.api_secret:
            headers["APCA-API-SECRET-KEY"] = self.api_secret
        return headers

    def _request(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        feed: Optional[str] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resolved_feed = self._resolve_feed(feed)
        query = dict(params or {})
        if resolved_feed:
            query["feed"] = resolved_feed

        headers = self._build_headers()

        status, data = self._transport(
            "GET",
            url,
            params=query,
            headers=headers,
            timeout=self.timeout,
            retries=self.retries,
            backoff=self.backoff,
            session=self._session,
        )
        if status != 401:
            return status, data

        self.log.warning(
            "[alpaca] auth 401 on %s feed=%s; retrying once", path, resolved_feed
        )
        status, data = self._transport(
            "GET",
            url,
            params=query,
            headers=headers,
            timeout=self.timeout,
            retries=self.retries,
            backoff=self.backoff,
            session=self._session,
        )
        if status != 401:
            return status, data

        detail = (data or {}).get("message") or (data or {}).get("error") or "401"
        guidance = (
            "Verify ALPACA_API_KEY / ALPACA_API_SECRET and ensure entitlement "
            f"for the '{resolved_feed}' data feed."
        )
        if self.force_yahoo_on_auth_error:
            guidance += " Yahoo fallback will be triggered."
        self.log.error(
            "[alpaca] persistent 401 feed=%s detail=%s. %s "
            "Set ALPACA_FORCE_YAHOO_ON_AUTH_ERROR=1 to auto-route to Yahoo.",
            resolved_feed,
            detail,
            guidance,
        )
        raise AlpacaAuthError(
            f"Alpaca authentication failed: {guidance}",
            fallback_to_yahoo=self.force_yahoo_on_auth_error,
        )
