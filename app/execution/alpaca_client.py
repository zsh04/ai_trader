from __future__ import annotations


class AlpacaClient:
    def __init__(self, key: str, secret: str, base_url: str):
        self.key = key
        self.secret = secret
        self.base_url = base_url

    def place_bracket_order(
        symbol: str,
        side: str,
        qty: int,
        tp_pct: float | None,
        sl_pct: float | None,
        extended_hours: bool = False,
    ) -> str:
        """
        TODO: implement with Alpaca REST v2 orders API.
        Return order id string.
        """
        # For now, pretend success and return a fake id
        return f"demo-{symbol.lower()}-{side}-{qty}"
