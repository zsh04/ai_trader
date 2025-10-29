from __future__ import annotations

import importlib
import logging
import os
from typing import Iterable, List, Tuple

from app.domain.watchlist_utils import normalize_symbols

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE = "textlist"
_WARNED_KEYS: set[str] = set()


def _warn_once(key: str, message: str, *args: object) -> None:
    if key in _WARNED_KEYS:
        return
    logger.warning(message, *args)
    _WARNED_KEYS.add(key)


def _import_source(module_name: str):
    primary = f"app.source.{module_name}"
    fallback = f"app.sources.{module_name}"
    try:
        return importlib.import_module(primary)
    except ModuleNotFoundError as exc:
        try:
            return importlib.import_module(fallback)
        except ModuleNotFoundError:
            raise exc


def _iter_symbols(payload: object) -> Iterable[str]:
    if payload is None:
        return []
    if isinstance(payload, dict) and "symbols" in payload:
        return payload.get("symbols") or []
    if isinstance(payload, (list, tuple, set)):
        return payload
    return [str(payload)]


def _fetch_symbols(source: str) -> List[str]:
    module_name = f"{source}_source"
    try:
        module = _import_source(module_name)
    except ModuleNotFoundError:
        _warn_once(f"import:{source}", "[watchlist] source=%s module missing", source)
        return []

    candidates = ("get_symbols", "fetch_symbols", "load_symbols")
    for attr in candidates:
        fn = getattr(module, attr, None)
        if callable(fn):
            try:
                result = fn()  # type: ignore[call-arg]
            except Exception as exc:  # pragma: no cover - defensive
                _warn_once(f"fetch:{source}", "[watchlist] source=%s failed: %s", source, exc)
                return []
            return list(_iter_symbols(result))

    _warn_once(f"missing-fn:{source}", "[watchlist] source=%s has no symbol provider", source)
    return []


def resolve_watchlist() -> Tuple[str, List[str]]:
    """
    Resolve the watchlist symbols based on ``WATCHLIST_SOURCE`` env var.

    Returns:
        Tuple of (source_name, normalized_symbols).
    """
    requested = (os.getenv("WATCHLIST_SOURCE") or _DEFAULT_SOURCE).strip().lower()
    source = requested or _DEFAULT_SOURCE

    if source == "scanner":
        _warn_once(
            "scanner-fallback",
            "[watchlist] source=scanner not implemented; falling back to textlist",
        )
        source = _DEFAULT_SOURCE
    elif source not in {"textlist", "finviz"}:
        _warn_once(
            f"unknown:{source}",
            "[watchlist] unknown source=%s; falling back to %s",
            source,
            _DEFAULT_SOURCE,
        )
        source = _DEFAULT_SOURCE

    symbols = _fetch_symbols(source)
    normalized = normalize_symbols(symbols)
    if not normalized and symbols:
        _warn_once(
            f"normalization-empty:{source}",
            "[watchlist] source=%s yielded unnormalized symbols; returning empty list",
            source,
        )
    if not normalized and not symbols:
        _warn_once(
            f"empty:{source}",
            "[watchlist] source=%s returned no symbols",
            source,
        )

    return source, normalized


__all__ = ["resolve_watchlist"]
