from fastapi import FastAPI
from app.utils.logging import get_logger
from app.scanners.premarket_scanner import scan_premarket, write_watchlist
from app.sessions.session_clock import SessionClock

app = FastAPI(title="AI Trading Agent")
log = get_logger(__name__)

# Simple session clock config (PT). Use config loader in production.
clock = SessionClock(
    tz="America/Los_Angeles",
    ranges={
        "PRE": ("04:00","09:30"),
        "REG-AM": ("09:30","11:30"),
        "REG-MID": ("11:30","14:00"),
        "REG-PM": ("14:00","16:00"),
        "AFT": ("16:00","20:00"),
    },
)

@app.get("/health")
def health():
    return {"ok": True, "session": clock.now_session()}

@app.post("/tasks/premarket-scan")
def task_premarket_scan():
    cands = scan_premarket()
    path = write_watchlist(cands)
    log.info(f"Wrote watchlist: {path}")
    return {"count": len(cands), "path": path}
