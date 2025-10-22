from fastapi import FastAPI
from app.scanners.premarket_scanner import premarket_watchlist, write_to_blob

app = FastAPI()

@app.post("/tasks/premarket-scan")
def premarket_scan():
    # TODO: source your symbol universe from config or a small list to start
    symbols = ["SPY","QQQ","AAPL","TSLA"]  # + your $1–$10 candidates from a screener later
    wl = premarket_watchlist(symbols)
    path = write_to_blob(wl)
    return {"count": len(wl), "blob": path}