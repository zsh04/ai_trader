# app/api/routes/watchlists.py
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.domain.watchlist_repo import WatchlistRepo

router = APIRouter(tags=["watchlists"])
_repo = WatchlistRepo()


class SaveWatchlistRequest(BaseModel):
    bucket: Optional[str] = Field(
        None, description="Bucket name (required for root POST)."
    )
    symbols: List[str] = Field(default_factory=list)
    tags: Optional[List[str]] = None
    source: str = "textlist"
    meta: Optional[dict] = None


class WatchlistRecord(BaseModel):
    bucket: str
    name: str
    asof_utc: str
    source: str
    count: int
    tags: List[str]
    symbols: List[str]
    meta: Dict[str, object] = Field(default_factory=dict)


def _format_doc(doc) -> Dict[str, object]:
    payload = doc.to_json()
    return {
        "bucket": payload["bucket"],
        "name": payload["bucket"],
        "asof_utc": payload["asof_utc"],
        "source": payload["source"],
        "count": len(payload.get("symbols") or []),
        "tags": payload.get("tags") or [],
        "symbols": payload.get("symbols") or [],
        "meta": payload.get("meta") or {},
    }


def _save_bucket(bucket: str, body: SaveWatchlistRequest) -> Dict[str, object]:
    if not body.symbols:
        raise HTTPException(status_code=422, detail="symbols list required")
    wl = _repo.save(
        bucket,
        body.symbols,
        source=body.source,
        tags=body.tags or [],
        meta=body.meta or {},
    )
    return _format_doc(wl)


@router.get("/", response_model=List[WatchlistRecord])
def list_watchlists(limit: int = Query(20, ge=1, le=200)) -> List[Dict[str, object]]:
    docs = _repo.list_latest(limit=limit)
    return [_format_doc(doc) for doc in docs]


@router.post("/", response_model=WatchlistRecord)
def create_watchlist(body: SaveWatchlistRequest) -> Dict[str, object]:
    if not body.bucket:
        raise HTTPException(status_code=422, detail="bucket is required")
    return _save_bucket(body.bucket, body)


@router.post("/{bucket}", response_model=WatchlistRecord)
def save_watchlist(bucket: str, body: SaveWatchlistRequest) -> Dict[str, object]:
    return _save_bucket(bucket, body)


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
