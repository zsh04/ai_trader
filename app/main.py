# app/main.py
import os
from fastapi import FastAPI, HTTPException
from datetime import datetime, timezone
from app.config import settings
from app.scanners.premarket_scanner import build_premarket_watchlist
from app.data.store import put_json, today_key
from app.utils.db import pg_engine
from sqlalchemy import text

app = FastAPI(title="AI Trader", version="0.1.0")

@app.get("/health")
def health():
    # Basic health; upgrade later with DB/Blob checks
    return {
        "status": "ok",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "tz": settings.tz
    }

@app.post("/tasks/premarket-scan")
def premarket_scan():
    wl = build_premarket_watchlist()
    if not wl:
        return {"ok": True, "message": "No candidates matched filters", "count": 0}

    # write to blob
    key = today_key("watchlists/premarket")
    uri = put_json(wl, key)

    # optional: log to DB if schema exists
    try:
        eng = pg_engine()
        with eng.begin() as cx:
            cx.execute(text("""
                insert into watchlist_log (id, as_of_utc, blob_path, count, kind)
                values (gen_random_uuid(), now(), :path, :n, 'PRE')
            """), {"path": key, "n": len(wl)})
    except Exception:
        # silent for MVP; we’ll add logging later
        pass

    return {"ok": True, "count": len(wl), "blob": uri, "path": key, "items": wl}