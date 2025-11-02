# app/adapters/market/alpaca_client.py
from __future__ import annotations

import ssl
import socket
import time
from contextlib import closing
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from loguru import logger

from app.utils import env as ENV
from app.utils.http import request_json

__all__ = ["AlpacaMarketClient", "AlpacaAuthError", "ping_alpaca", "AlpacaPingError"]


_ALLOWED_FEEDS = {"iex", "sip"}


# --- Alpaca trading API ping helpers ---
class AlpacaPingError(Exception):
    """Raised when the Alpaca trading API ping fails."""

    pass


def _trading_base_url() -> str:
    """
    Retrieves the trading base URL from environment variables.

    Returns:
        str: The trading base URL.
    """
    # Prefer explicit trading base URL if present; fallback to paper trading.
    from app.utils import env as ENV

    return (
        getattr(ENV, "ALPACA_TRADING_BASE_URL", None)
        or getattr(ENV, "ALPACA_BASE_URL", None)
        or "https://paper-api.alpaca.markets"
    ).rstrip("/")


def _api_headers() -> Dict[str, str]:
    """
    Builds the API headers for Alpaca API requests.

    Returns:
        Dict[str, str]: A dictionary of API headers.

    Raises:
        AlpacaPingError: If API key or secret is missing.
    """
    from app.utils import env as ENV

    key = (
        getattr(ENV, "ALPACA_API_KEY", None)
        or getattr(ENV, "ALPACA_API_KEY_ID", None)
    )
    secret = (
        getattr(ENV, "ALPACA_API_SECRET", None)
        or getattr(ENV, "ALPACA_API_SECRET_KEY", None)
    )
    if not key or not secret:
        raise AlpacaPingError(
            "Missing ALPACA_API_KEY / ALPACA_API_SECRET in environment"
        )
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _normalize_symbols(symbols: Iterable[str]) -> List[str]:
    """
    Normalizes a list of symbols.

    Args:
        symbols (Iterable[str]): A list of symbols.

    Returns:
        List[str]: A list of normalized symbols.
    """
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
        """
        Initializes the AlpacaAuthError.

        Args:
            message (str): The error message.
            fallback_to_yahoo (bool): Whether to fallback to Yahoo.
        """
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
    ) -> None:
        """
        Initializes the AlpacaMarketClient.

        Args:
            api_key (Optional[str]): The Alpaca API key.
            api_secret (Optional[str]): The Alpaca API secret.
            base_url (Optional[str]): The Alpaca API base URL.
            default_feed (Optional[str]): The default data feed.
            timeout (Optional[int]): The request timeout.
            retries (Optional[int]): The number of retries.
            backoff (Optional[float]): The backoff factor for retries.
            force_yahoo_on_auth_error (Optional[bool]): Whether to fallback to Yahoo on auth error.
            transport: The transport function.
            session: The request session.
        """
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

    # --------------------------------------------------------------------- #
    # Public API                                                            #
    # --------------------------------------------------------------------- #
    def snapshots(
        self, symbols: Sequence[str], *, feed: Optional[str] = None
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Retrieves snapshots for a list of symbols.

        Args:
            symbols (Sequence[str]): A list of symbols.
            feed (Optional[str]): The data feed to use.

        Returns:
            Tuple[int, Dict[str, Any]]: A tuple of status code and a dictionary of snapshots.
        """
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
        """
        Resolves the data feed.

        Args:
            feed (Optional[str]): The data feed.

        Returns:
            str: The resolved data feed.
        """
        if not feed:
            return self.default_feed
        value = feed.strip().lower()
        if value in _ALLOWED_FEEDS:
            return value
        logger.warning(
            "[alpaca] unknown feed={}; defaulting to {}", feed, self.default_feed
        )
        return self.default_feed

    def _build_headers(self) -> Dict[str, str]:
        """
        Builds the request headers.

        Returns:
            Dict[str, str]: A dictionary of request headers.
        """
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
        """
        Makes a request to the Alpaca API.

        Args:
            path (str): The API path.
            params (Optional[Dict[str, Any]]): The request parameters.
            feed (Optional[str]): The data feed.

        Returns:
            Tuple[int, Dict[str, Any]]: A tuple of status code and response data.

        Raises:
            AlpacaAuthError: If authentication fails.
        """
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

        logger.warning(
            "[alpaca] auth 401 on {} feed={}; retrying once", path, resolved_feed
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
        logger.error(
            "[alpaca] persistent 401 feed={} detail={}. {} "
            "Set ALPACA_FORCE_YAHOO_ON_AUTH_ERROR=1 to auto-route to Yahoo.",
            resolved_feed,
            detail,
            guidance,
        )
        raise AlpacaAuthError(
            f"Alpaca authentication failed: {guidance}",
            fallback_to_yahoo=self.force_yahoo_on_auth_error,
        )


# --- Alpaca trading API ping endpoint ---
def ping_alpaca(feed: str | None = None, timeout_sec: float = 4.0) -> tuple[bool, dict]:
    """
    Connectivity check to Alpaca market data edge.
    We do a DNS + TCP + TLS handshake to data.alpaca.markets:443 (no creds required).

    Args:
        feed (str | None): The data feed to use.
        timeout_sec (float): The timeout in seconds.

    Returns:
        tuple[bool, dict]: A tuple of success status and metadata.

    Raises:
        AlpacaPingError: If the ping fails.
    """
    host = "data.alpaca.markets"
    port = 443
    feed = (feed or "iex").lower()

    start = time.perf_counter()
    try:
        # DNS + TCP connect
        with closing(socket.create_connection((host, port), timeout=timeout_sec)) as sock:
            # TLS handshake
            ctx = ssl.create_default_context()
            with closing(ctx.wrap_socket(sock, server_hostname=host)) as ssock:
                # Optional: send minimal data or just handshake and close
                pass

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return True, {
            "host": host,
            "port": port,
            "feed": feed,
            "latency_ms": elapsed_ms,
            "method": "tcp+tls",
        }
    except Exception as e:
        # Normalize into our domain error so caller can mark degraded
        raise AlpacaPingError(f"network/transport error: {e!s}")
