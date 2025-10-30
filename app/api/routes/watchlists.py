# app/api/routes/watchlists.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

from app.domain.watchlist_repo import WatchlistRepo

router = APIRouter(prefix="/watchlists", tags=["watchlists"])
_repo = WatchlistRepo()

class SaveWatchlistRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list)
    tags: Optional[List[str]] = None
    source: str = "textlist"
    meta: Optional[dict] = None

@router.post("/{bucket}")
def save_watchlist(bucket: str, body: SaveWatchlistRequest):
    wl = _repo.save(bucket, body.symbols, source=body.source, tags=body.tags or [], meta=body.meta or {})
    return {"ok": True, "bucket": wl.bucket, "asof_utc": wl.asof_utc.isoformat(), "count": len(wl.symbols)}

@router.get("/{bucket}/latest")
def get_latest(bucket: str):
    wl = _repo.latest(bucket)
    if not wl:
        raise HTTPException(404, "not found")
    return wl.to_json()

@router.get("/{bucket}/{yyyymmdd}")
def get_by_date(bucket: str, yyyymmdd: str):
    if len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        raise HTTPException(400, "yyyymmdd required")
    wl = _repo.nearest_on(bucket, yyyymmdd)
    if not wl:
        raise HTTPException(404, "not found")
    return wl.to_json()