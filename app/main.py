# app/main.py (health++)
import os
from fastapi import FastAPI, HTTPException, Request, Query
from datetime import datetime, timezone
from sqlalchemy import text
from app.config import settings
from app.adapters.db.postgres import make_engine, make_session_factory
from app.scanners.watchlist_builder import build_watchlist
from app.adapters.storage.blob import *
from pydantic import BaseModel
from typing import List, Optional
from app.adapters.notifiers.telegram import send_message
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

@app.post("/tasks/watchlist")
def watchlist_task(
    symbols: Optional[List[str]] = Query(None),
    include_filters: bool = True,
    passthrough: bool = False,
    include_ohlcv: bool = True,
    debug: bool = False,
):
    wl = build_watchlist(
        symbols=symbols,
        include_filters=include_filters,
        passthrough=passthrough,
        include_ohlcv=include_ohlcv,
    )
    return wl