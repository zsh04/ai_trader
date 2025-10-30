# app/domain/watchlist_service.py
from __future__ import annotations

import importlib
import logging
import os
import sys
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
    """
    Resolve a source module, favoring monkeypatched entries used by tests:
      - First, look in sys.modules for 'app.source.{name}' or 'app.sources.{name}'
      - Then, try to import 'app.source.{name}', falling back to 'app.sources.{name}'
    """
    primary = f"app.source.{module_name}"
    fallback = f"app.sources.{module_name}"

    # Respect test monkeypatching and already-loaded modules
    if primary in sys.modules:
        return sys.modules[primary]
    if fallback in sys.modules:
        return sys.modules[fallback]

    # Import normally
    try:
        return importlib.import_module(primary)
    except ModuleNotFoundError as exc:
        try:
            return importlib.import_module(fallback)
        except ModuleNotFoundError:
            # Re-raise the original to keep the ‘primary’ context
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
    """
    Load symbols from a source module. The module may expose one of:
      - get_symbols()
      - fetch_symbols()
      - load_symbols()
    """
    module_name = f"{source}_source"
    try:
        module = _import_source(module_name)
    except ModuleNotFoundError:
        _warn_once(f"import:{source}", "[watchlist] source=%s module missing", source)
        return []

    for attr in ("get_symbols", "fetch_symbols", "load_symbols"):
        fn = getattr(module, attr, None)
        if callable(fn):
            try:
                result = fn()  # type: ignore[misc]
            except Exception as exc:  # pragma: no cover (defensive)
                _warn_once(
                    f"fetch:{source}",
                    "[watchlist] source=%s failed: %s",
                    source,
                    exc,
                )
                return []
            return list(_iter_symbols(result))

    _warn_once(
        f"missing-fn:{source}",
        "[watchlist] source=%s has no symbol provider",
        source,
    )
    return []


def _parse_manual_from_env() -> List[str]:
    """
    Interpret WATCHLIST_TEXT as a comma/whitespace separated symbol list.
    """
    raw = os.getenv("WATCHLIST_TEXT", "") or ""
    if not raw.strip():
        return []
    # split by comma first, then strip; also split spaces within each chunk
    parts: list[str] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        # If the chunk still contains whitespace, split that too
        parts.extend(chunk.split())
    return parts


def _apply_max_cap(symbols: List[str]) -> List[str]:
    """
    Truncate to MAX_WATCHLIST if set to a positive int.
    """
    cap_raw = os.getenv("MAX_WATCHLIST", "").strip()
    cap: int | None = None
    if cap_raw:
        try:
            cap = int(cap_raw)
        except ValueError:
            _warn_once(
                "bad-cap",
                "[watchlist] invalid MAX_WATCHLIST=%r; ignoring cap",
                cap_raw,
            )
    if cap and cap > 0 and len(symbols) > cap:
        return symbols[:cap]
    return symbols


def resolve_watchlist() -> Tuple[str, List[str]]:
    """
    Resolve the watchlist symbols based on WATCHLIST_SOURCE env var.

    Returns:
        (source_name, normalized_symbols).
    """
    requested = (os.getenv("WATCHLIST_SOURCE") or _DEFAULT_SOURCE).strip().lower()
    source = requested or _DEFAULT_SOURCE

    # Normalize source selection
    if source == "scanner":
        _warn_once(
            "scanner-fallback",
            "[watchlist] source=scanner not implemented; falling back to textlist",
        )
        source = _DEFAULT_SOURCE
    elif source not in {"textlist", "finviz", "manual"}:
        _warn_once(
            f"unknown:{source}",
            "[watchlist] unknown source=%s; falling back to %s",
            source,
            _DEFAULT_SOURCE,
        )
        source = _DEFAULT_SOURCE

    # Gather symbols by source
    if source == "manual":
        symbols = _parse_manual_from_env()
    else:
        symbols = _fetch_symbols(source)

    # Normalize and cap
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

    capped = _apply_max_cap(normalized)
    return source, capped


__all__ = ["resolve_watchlist"]