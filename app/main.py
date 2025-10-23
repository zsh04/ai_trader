# app/main.py (health++)
import os
from fastapi import FastAPI, HTTPException, Request, Query
from datetime import datetime, timezone
from sqlalchemy import text
from app.config import settings
from app.utils.db import pg_engine
from app.scanners.premarket_scanner import build_premarket_watchlist
from app.data.store import put_json, today_key
from pydantic import BaseModel
from typing import List, Optional
from app.utils.telegram import send_message
from app.utils.formatting import format_watchlist_telegram
from app.data.data_client import batch_latest_ohlcv

app = FastAPI(title="AI Trader", version="0.1.0")

def _check_blob() -> tuple[bool, str]:
    try:
        from azure.storage.blob import BlobServiceClient
        conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if conn:
            bsc = BlobServiceClient.from_connection_string(conn)
        else:
            from app.config import settings
            bsc = BlobServiceClient(
                f"https://{settings.blob_account}.blob.core.windows.net",
                credential=settings.blob_key,
            )
        # lightweight call
        next(bsc.list_containers(), None)
        return True, "ok"
    except Exception as e:
        return False, str(e)

def _check_db() -> tuple[bool, str]:
    try:
        eng = pg_engine()
        with eng.begin() as cx:
            cx.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as e:
        return False, str(e)

@app.get("/health")
def health():
    blob_ok, blob_msg = _check_blob()
    db_ok, db_msg = _check_db()
    status = "ok" if (blob_ok and db_ok) else "degraded"
    return {
        "status": status,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "tz": settings.tz,
        "blob": {"ok": blob_ok, "msg": blob_msg[:160]},
        "db": {"ok": db_ok, "msg": db_msg[:160]},
    }
class ScanRequest(BaseModel):
    symbols: Optional[List[str]] = None
    debug: bool = False

@app.post("/tasks/premarket-scan")
def premarket_scan(
    body: ScanRequest | None = None,
    symbols: Optional[List[str]] = Query(None),
    debug: bool = False,
    passthrough: bool = False,
    include_ohlcv: bool = True,   # <-- default ON
):
    custom = symbols or (body.symbols if body else None)

    if passthrough:
        if not custom:
            raise HTTPException(status_code=400, detail="Provide symbols via ?symbols=AAA&symbols=BBB or body {symbols:[...]}")
        syms = [s.strip().upper() for s in custom if s and s.strip()]
        items = [{"symbol": s} for s in syms]
        if include_ohlcv:
            snapmap = batch_latest_ohlcv(syms)
            for it in items:
                m = snapmap.get(it["symbol"], {})
                it["last"] = m.get("last", 0.0)
                it["o"] = m.get("ohlcv", {}).get("o", 0.0)
                it["h"] = m.get("ohlcv", {}).get("h", 0.0)
                it["l"] = m.get("ohlcv", {}).get("l", 0.0)
                it["c"] = m.get("ohlcv", {}).get("c", 0.0)
                it["v"] = m.get("ohlcv", {}).get("v", 0)
    else:
        items = build_premarket_watchlist(debug=debug, symbols=custom)

    key = today_key("watchlists/manual" if passthrough else "watchlists/premarket")
    put_json(items, key)

    title = "AI Trader • Manual Watchlist" if passthrough else "AI Trader • Premarket Watchlist"
    text = format_watchlist_telegram(items, title=title, blob_path=key)
    send_message(text)

    return {"ok": True, "count": len(items), "path": key, "items": items}