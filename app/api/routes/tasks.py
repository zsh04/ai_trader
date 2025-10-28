from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from app.domain.watchlist_service import resolve_watchlist

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


def _send_watchlist(
    session: str, items: List[dict], *, title: str, chat_id: Optional[int | str] = None
) -> bool:
    try:
        from app.adapters.notifiers.telegram import send_watchlist  # type: ignore

        return send_watchlist(session, items, chat_id=chat_id, title=title)
    except Exception:
        return False


def _build_watchlist(
    symbols: Optional[List[str]],
    *,
    include_filters: bool,
    include_ohlcv: bool,
    limit: int,
) -> Dict[str, Any]:
    try:
        from app.scanners.watchlist_builder import build_watchlist  # type: ignore

        return build_watchlist(
            symbols=symbols,
            include_filters=include_filters,
            include_ohlcv=include_ohlcv,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"watchlist error: {e!s}") from e


@router.post("/watchlist", tags=["watchlist"])
def task_watchlist(
    symbols: Optional[List[str]] = Query(None),
    include_filters: bool = Query(True),
    include_ohlcv: bool = Query(True),
    limit: int = Query(15, ge=1, le=100),
    notify: bool = Query(False),
    title: Optional[str] = Query(None),
    chat_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    wl = _build_watchlist(
        symbols=symbols,
        include_filters=include_filters,
        include_ohlcv=include_ohlcv,
        limit=limit,
    )
    if notify and isinstance(wl, dict):
        session = wl.get("session", "regular")
        items = wl.get("items", [])
        _send_watchlist(
            session, items, title=title or "AI Trader • Watchlist", chat_id=chat_id
        )
    return wl

@router.get("/watchlist")
def get_watchlist() -> Dict[str, Any]:
    source, symbols = resolve_watchlist()
    payload = {"source": source, "count": len(symbols), "symbols": symbols}
    logger.info("[watchlist] source=%s count=%d", source, payload["count"])
    return payload
