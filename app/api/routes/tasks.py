from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from app.domain.watchlist_service import resolve_watchlist

tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])
public_router = APIRouter(tags=["watchlist"])


_build_counters: dict[str, dict[str, int]] = {}


def _increment_build_counter(source: str, ok: bool) -> None:
    """
    Increments the build counter for a given source.

    Args:
        source (str): The source of the watchlist.
        ok (bool): Whether the build was successful.
    """
    bucket = _build_counters.setdefault(source, {"ok": 0, "error": 0})
    bucket["ok" if ok else "error"] += 1


def get_build_counters() -> dict[str, dict[str, int]]:
    """
    Returns the build counters.

    Returns:
        dict[str, dict[str, int]]: A dictionary of build counters.
    """
    return {k: v.copy() for k, v in _build_counters.items()}


def _build_watchlist(
    symbols: Optional[List[str]],
    *,
    include_filters: bool,
    include_ohlcv: bool,
    limit: int,
) -> Dict[str, Any]:
    """
    Builds a watchlist.

    Args:
        symbols (Optional[List[str]]): A list of symbols to include.
        include_filters (bool): Whether to include filters.
        include_ohlcv (bool): Whether to include OHLCV data.
        limit (int): The maximum number of symbols to include.

    Returns:
        Dict[str, Any]: The watchlist.

    Raises:
        HTTPException: If an error occurs while building the watchlist.
    """
    start = time.perf_counter()
    source = "manual"
    try:
        from app.scanners.watchlist_builder import build_watchlist

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
            "[watchlist:build] {}",
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
            "[watchlist:build] {}",
            {
                "source": source,
                "count": 0,
                "duration_ms": round(duration_ms, 2),
                "ok": False,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail=f"watchlist error: {e!s}") from e


SYMBOLS_QUERY = Query(default=None)
BOOL_TRUE_QUERY = Query(default=True)
LIMIT_QUERY = Query(default=15, ge=1, le=100)


@tasks_router.post("/watchlist", tags=["watchlist"])
def task_watchlist(
    symbols: Optional[List[str]] = SYMBOLS_QUERY,
    include_filters: bool = BOOL_TRUE_QUERY,
    include_ohlcv: bool = BOOL_TRUE_QUERY,
    limit: int = LIMIT_QUERY,
) -> Dict[str, Any]:
    """
    Builds a watchlist.

    Args:
        symbols (Optional[List[str]]): A list of symbols to include.
        include_filters (bool): Whether to include filters.
        include_ohlcv (bool): Whether to include OHLCV data.
        limit (int): The maximum number of symbols to include.

    Returns:
        Dict[str, Any]: The watchlist.
    """
    wl = _build_watchlist(
        symbols=symbols,
        include_filters=include_filters,
        include_ohlcv=include_ohlcv,
        limit=limit,
    )
    return wl


def _get_watchlist_payload() -> Dict[str, Any]:
    """
    Resolves and returns the watchlist payload.

    Returns:
        Dict[str, Any]: The watchlist payload.
    """
    source, symbols = resolve_watchlist()
    payload = {"source": source, "count": len(symbols), "symbols": symbols}
    logger.info("[watchlist] source={} count={}", source, payload["count"])
    return payload


@tasks_router.get("/watchlist")
def get_watchlist_tasks() -> Dict[str, Any]:
    """
    Returns the current watchlist.

    Returns:
        Dict[str, Any]: The current watchlist.
    """
    return _get_watchlist_payload()


@public_router.get("/watchlist")
def get_watchlist_public() -> Dict[str, Any]:
    """
    Returns the current watchlist.

    Returns:
        Dict[str, Any]: The current watchlist.
    """
    return _get_watchlist_payload()


__all__ = ["tasks_router", "public_router"]
