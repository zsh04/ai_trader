from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
import json
import time

from app.domain.watchlist_service import resolve_watchlist

tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])
public_router = APIRouter(tags=["watchlist"])
logger = logging.getLogger(__name__)


def _send_watchlist(
    session: str, items: List[dict], *, title: str, chat_id: Optional[int | str] = None
) -> bool:
    try:
        from app.adapters.notifiers.telegram import send_watchlist  # type: ignore

        return send_watchlist(session, items, chat_id=chat_id, title=title)
    except Exception:
        return False


_build_counters: dict[str, dict[str, int]] = {}


def _increment_build_counter(source: str, ok: bool) -> None:
    bucket = _build_counters.setdefault(source, {"ok": 0, "error": 0})
    bucket["ok" if ok else "error"] += 1


def get_build_counters() -> dict[str, dict[str, int]]:
    return {k: v.copy() for k, v in _build_counters.items()}


def _build_watchlist(
    symbols: Optional[List[str]],
    *,
    include_filters: bool,
    include_ohlcv: bool,
    limit: int,
) -> Dict[str, Any]:
    start = time.perf_counter()
    source = "manual"
    try:
        from app.scanners.watchlist_builder import build_watchlist  # type: ignore

        result = build_watchlist(
            symbols=symbols,
            include_filters=include_filters,
            include_ohlcv=include_ohlcv,
            limit=limit,
        )
        if isinstance(result, dict):
            source = result.get("source", "scanner")
        duration_ms = (time.perf_counter() - start) * 1000.0
        _increment_build_counter(source, True)
        logger.info(
            "[watchlist:build] %s",
            {
                "source": source,
                "count": result.get("count", 0) if isinstance(result, dict) else 0,
                "duration_ms": round(duration_ms, 2),
                "ok": True,
            },
        )
        return result
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000.0
        _increment_build_counter(source, False)
        logger.warning(
            "[watchlist:build] %s",
            {
                "source": source,
                "count": 0,
                "duration_ms": round(duration_ms, 2),
                "ok": False,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail=f"watchlist error: {e!s}") from e


@tasks_router.post("/watchlist", tags=["watchlist"])
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

def _get_watchlist_payload() -> Dict[str, Any]:
    source, symbols = resolve_watchlist()
    payload = {"source": source, "count": len(symbols), "symbols": symbols}
    logger.info("[watchlist] source=%s count=%d", source, payload["count"])
    return payload

@tasks_router.get("/watchlist")
def get_watchlist_tasks() -> Dict[str, Any]:
    return _get_watchlist_payload()

@public_router.get("/watchlist")
def get_watchlist_public() -> Dict[str, Any]:
    return _get_watchlist_payload()

__all__ = ["tasks_router", "public_router"]
