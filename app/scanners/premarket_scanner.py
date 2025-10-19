import json, datetime
from app.data.data_client import DataClient
from app.data.store import Store

def premarket_watchlist(symbols):
    api = DataClient()
    cands = []
    for s in symbols:
        q = api.get_premarket_quotes(s)
        # TODO: compute gap%, RVOL, spread% (you’ll add OHLCV + volume pulls)
        # Placeholder spread from bid/ask if present:
        bid = q.get("quote", {}).get("bp")
        ask = q.get("quote", {}).get("ap")
        if bid and ask and 1 <= ((bid+ask)/2) <= 10:
            spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
            if spread_pct <= 0.75:
                cands.append({"symbol": s, "spread_pct": spread_pct})
    return cands

def write_to_blob(cands):
    dt = datetime.datetime.now().strftime("%Y-%m-%d")
    Store().upload_text(f"watchlists/{dt}.json", json.dumps(cands, indent=2))
    return f"watchlists/{dt}.json"