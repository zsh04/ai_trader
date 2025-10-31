from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import requests


class ExecutionError(RuntimeError):
    """Raised when an order placement or broker interaction fails."""


class AlpacaClient:
    """
    A minimal and safe Alpaca Trading v2 execution adapter.

    Attributes:
        key (str): The Alpaca API key.
        secret (str): The Alpaca API secret.
        base_url (str): The base URL for the Alpaca API.
        data_url (str): The base URL for the Alpaca data API.
        timeout (float): The request timeout in seconds.
        retries (int): The number of retries for failed requests.
        backoff (float): The backoff factor for retries.
        log (logging.Logger): The logger instance.
    """

    def __init__(
        self,
        key: str,
        secret: str,
        base_url: str,
        *,
        data_url: str | None = None,
        timeout: float = 10.0,
        retries: int = 2,
        backoff: float = 1.5,
        logger: logging.Logger | None = None,
    ) -> None:
        """
        Initializes the AlpacaClient.

        Args:
            key (str): The Alpaca API key.
            secret (str): The Alpaca API secret.
            base_url (str): The base URL for the Alpaca API.
            data_url (str | None): The base URL for the Alpaca data API.
            timeout (float): The request timeout in seconds.
            retries (int): The number of retries for failed requests.
            backoff (float): The backoff factor for retries.
            logger (logging.Logger | None): The logger instance.
        """
        self.key = key
        self.secret = secret
        self.base_url = base_url.rstrip("/")
        self.data_url = (data_url or "https://data.alpaca.markets").rstrip("/")
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff = max(0.0, backoff)
        self.log = logger or logging.getLogger(__name__)

    def _auth_headers(self) -> Dict[str, str]:
        """
        Returns the authentication headers for API requests.

        Returns:
            Dict[str, str]: A dictionary of authentication headers.
        """
        return {
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ai-trader/0.1 (+alpaca-client)",
        }

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Makes an HTTP request with retries.

        Args:
            method (str): The HTTP method.
            url (str): The URL to request.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response.
        """
        headers = kwargs.pop("headers", {})
        merged_headers = {**self._auth_headers(), **headers}
        attempt = 0
        while True:
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=merged_headers,
                    timeout=self.timeout,
                    **kwargs,
                )
                if (
                    resp.status_code in (429, 500, 502, 503, 504)
                    and attempt < self.retries
                ):
                    delay = self.backoff * (attempt + 1)
                    self.log.warning(
                        "HTTP %s %s -> %s; retrying in %.1fs (attempt %s/%s)",
                        method,
                        url,
                        resp.status_code,
                        delay,
                        attempt + 1,
                        self.retries,
                    )
                    time.sleep(delay)
                    attempt += 1
                    continue
                return resp
            except requests.RequestException as e:
                if attempt < self.retries:
                    delay = self.backoff * (attempt + 1)
                    self.log.warning(
                        "HTTP %s %s exception: %s; retrying in %.1fs (attempt %s/%s)",
                        method,
                        url,
                        e,
                        delay,
                        attempt + 1,
                        self.retries,
                    )
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise

    def health_check(self) -> bool:
        """
        Checks the health of the Alpaca API.

        Returns:
            bool: True if the API is healthy, False otherwise.
        """
        url = f"{self.base_url}/v2/account"
        try:
            r = self._request("GET", url)
            ok = 200 <= r.status_code < 300
            if not ok:
                self.log.error(
                    "Alpaca health_check failed: %s %s", r.status_code, r.text
                )
            return ok
        except Exception as e:
            self.log.exception("Alpaca health_check exception: %s", e)
            return False

    def get_last_price(self, symbol: str) -> float:
        """
        Gets the last price for a symbol.

        Args:
            symbol (str): The symbol to get the last price for.

        Returns:
            float: The last price for the symbol.
        """
        url = f"{self.data_url}/v2/stocks/{symbol}/trades/latest"
        r = self._request("GET", url)
        if not (200 <= r.status_code < 300):
            raise ExecutionError(
                f"Failed to fetch last price for {symbol}: {r.status_code} {r.text}"
            )
        payload = r.json()
        trade = (payload or {}).get("trade") or {}
        p = trade.get("p")
        if p is None:
            raise ExecutionError(
                f"Missing trade price for {symbol}: {json.dumps(payload)[:200]}"
            )
        return float(p)

    def place_bracket_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        tp_pct: float | None,
        sl_pct: float | None,
        *,
        extended_hours: bool = False,
        time_in_force: str = "day",
        entry_price: float | None = None,
        sl_limit_offset: float = 0.0,
    ) -> str:
        """
        Places a bracket order.

        Args:
            symbol (str): The symbol to place the order for.
            side (str): The side of the order ('buy' or 'sell').
            qty (int): The quantity of the order.
            tp_pct (float | None): The take profit percentage.
            sl_pct (float | None): The stop loss percentage.
            extended_hours (bool): Whether to allow extended hours trading.
            time_in_force (str): The time in force for the order.
            entry_price (float | None): The entry price for the order.
            sl_limit_offset (float): The stop loss limit offset.

        Returns:
            str: The order ID.
        """
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if qty <= 0:
            raise ValueError("qty must be positive")

        tp_price: Optional[float] = None
        sl_price: Optional[float] = None
        sl_limit_price: Optional[float] = None

        if (tp_pct is not None or sl_pct is not None) and entry_price is None:
            entry_price = self.get_last_price(symbol)

        if entry_price is not None:
            if tp_pct is not None:
                if side == "buy":
                    tp_price = entry_price * (1.0 + tp_pct)
                else:
                    tp_price = entry_price * (1.0 - tp_pct)
            if sl_pct is not None:
                if side == "buy":
                    sl_price = entry_price * (1.0 - sl_pct)
                    sl_limit_price = (
                        sl_price - sl_limit_offset if sl_limit_offset > 0 else None
                    )
                else:
                    sl_price = entry_price * (1.0 + sl_pct)
                    sl_limit_price = (
                        sl_price + sl_limit_offset if sl_limit_offset > 0 else None
                    )

        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "market",
            "time_in_force": time_in_force,
            "qty": qty,
            "extended_hours": bool(extended_hours),
        }

        if tp_price is not None or sl_price is not None:
            payload["order_class"] = "bracket"
            if tp_price is not None:
                payload["take_profit"] = {"limit_price": round(float(tp_price), 2)}
            if sl_price is not None:
                stop_leg: Dict[str, Any] = {"stop_price": round(float(sl_price), 2)}
                if sl_limit_price is not None:
                    stop_leg["limit_price"] = round(float(sl_limit_price), 2)
                payload["stop_loss"] = stop_leg

        url = f"{self.base_url}/v2/orders"
        r = self._request("POST", url, json=payload)
        if not (200 <= r.status_code < 300):
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text}
            self.log.error("Order rejected (%s): %s", r.status_code, data)
            raise ExecutionError(f"Order rejected: {r.status_code} {data}")
        res = r.json()
        order_id = (res or {}).get("id")
        if not order_id:
            raise ExecutionError(
                f"Missing order id in response: {json.dumps(res)[:200]}"
            )
        self.log.info(
            "Placed %s %s x%s (bracket=%s) → id=%s",
            side,
            symbol,
            qty,
            "yes" if "order_class" in payload else "no",
            order_id,
        )
        return str(order_id)
