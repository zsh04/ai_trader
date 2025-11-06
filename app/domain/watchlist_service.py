"""Domain helpers for resolving watchlists from environment configuration."""
from __future__ import annotations

import os
from typing import List, Tuple

from loguru import logger

from app.services.watchlist_service import build_watchlist
from app.services.watchlist_sources import (
    fetch_alpha_vantage_symbols,
    fetch_finnhub_symbols,
    fetch_twelvedata_symbols,
)
from app.domain.watchlist_utils import normalize_symbols

_ALLOWED_SOURCES = {"auto", "alpha", "finnhub", "textlist", "manual", "twelvedata"}
_DEFAULT_SOURCE = "textlist"

_COUNTERS: dict[str, dict[str, int]] = {}
_WARNED_KEYS: set[str] = set()


def _counter(name: str) -> dict[str, int]:
    bucket = _COUNTERS.setdefault(name, {"ok": 0, "error": 0})
    return bucket


def get_watchlist_counters() -> dict[str, dict[str, int]]:
    return {k: v.copy() for k, v in _COUNTERS.items()}


def _parse_manual_from_env() -> List[str]:
    raw = os.getenv("WATCHLIST_TEXT", "")
    if not raw.strip():
        _warn_once("manual_empty", "[watchlist] manual source enabled but WATCHLIST_TEXT is empty")
        return []
    tokens: List[str] = []
    for chunk in raw.replace("\n", " ").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        tokens.extend(chunk.split())
    return tokens


def resolve_watchlist() -> Tuple[str, List[str]]:
    requested = (os.getenv("WATCHLIST_SOURCE") or "auto").strip().lower()
    source = requested if requested in _ALLOWED_SOURCES else _DEFAULT_SOURCE
    if requested not in _ALLOWED_SOURCES:
        _warn_once(
            f"invalid_source:{requested}",
            "[watchlist] invalid WATCHLIST_SOURCE '%s'; using '%s' instead" % (requested, _DEFAULT_SOURCE),
        )

    symbols: List[str] = []
    used_source = source
    counter = _counter(source)
    try:
        if source == "manual":
            symbols = _parse_manual_from_env()
        elif source == "textlist":
            symbols = build_watchlist(source="textlist")
        elif source == "alpha":
            symbols = fetch_alpha_vantage_symbols()
        elif source == "finnhub":
            symbols = fetch_finnhub_symbols()
        elif source == "twelvedata":
            symbols = fetch_twelvedata_symbols()
        elif source == "auto":
            symbols = fetch_alpha_vantage_symbols()
            used_source = "alpha"
            if not symbols:
                symbols = fetch_finnhub_symbols()
                used_source = "finnhub"
            if not symbols:
                symbols = build_watchlist(source="textlist")
                used_source = "textlist"
            if not symbols:
                symbols = fetch_twelvedata_symbols()
                used_source = "twelvedata"
        else:
            symbols = build_watchlist(source=_DEFAULT_SOURCE)
            used_source = _DEFAULT_SOURCE
        normalized = normalize_symbols(symbols)
        max_raw = (os.getenv("MAX_WATCHLIST") or "").strip()
        try:
            max_count = int(max_raw)
        except ValueError:
            max_count = None
            if max_raw:
                _warn_once(f"invalid_max:{max_raw}", "[watchlist] MAX_WATCHLIST must be integer; ignoring value '%s'" % max_raw)
        if max_count and max_count > 0:
            normalized = normalized[:max_count]
        counter["ok"] += 1
        return used_source, normalized
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("[watchlist] resolve failed source=%s", source)
        counter["error"] += 1
        return source, []


def _warn_once(key: str, message: str) -> None:
    if key in _WARNED_KEYS:
        return
    logger.warning(message)
    _WARNED_KEYS.add(key)
