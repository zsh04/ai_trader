# Minimal Alpaca client wrapper (paper trading) – placeholder.
class AlpacaClient:
    def __init__(self, key: str, secret: str, base_url: str):
        self.key = key
        self.secret = secret
        self.base_url = base_url

    def place_bracket_order(self, symbol: str, qty: int, side: str, limit_price: float, tp: float, sl: float, extended_hours: bool = False):
        # TODO: call Alpaca API
        return {"id": "demo-order", "status": "accepted"}
