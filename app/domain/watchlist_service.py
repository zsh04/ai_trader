# app/domain/watchlist_service.py
from __future__ import annotations

import importlib
import logging
import os
import sys
import time
from typing import Dict, Iterable, List, Tuple

from app.domain.watchlist_utils import normalize_symbols

_COUNTERS: Dict[str, Dict[str, int]] = {}


def _get_counter(name: str) -> Dict[str, int]:
    """
    Returns a counter for a given name.

    Args:
        name (str): The name of the counter.

    Returns:
        Dict[str, int]: A dictionary with the counter values.
    """
    bucket = _COUNTERS.setdefault(name, {"ok": 0, "error": 0})
    return bucket


def get_counters() -> Dict[str, Dict[str, int]]:
    """
    Returns all counters.

    Returns:
        Dict[str, Dict[str, int]]: A dictionary with all counter values.
    """
    return {k: v.copy() for k, v in _COUNTERS.items()}

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE = "textlist"
_WARNED_KEYS: set[str] = set()


def _warn_once(key: str, message: str, *args: object) -> None:
    """
    Logs a warning message once.

    Args:
        key (str): The key to identify the warning.
        message (str): The warning message.
        *args (object): The arguments for the warning message.
    """
    if key in _WARNED_KEYS:
        return
    logger.warning(message, *args)
    _WARNED_KEYS.add(key)


def _import_source(module_name: str):
    """
    Imports a source module.

    Args:
        module_name (str): The name of the module to import.

    Returns:
        The imported module.
    """
    primary = f"app.source.{module_name}"
    fallback = f"app.sources.{module_name}"

    if primary in sys.modules:
        return sys.modules[primary]
    if fallback in sys.modules:
        return sys.modules[fallback]

    try:
        return importlib.import_module(primary)
    except ModuleNotFoundError as exc:
        try:
            return importlib.import_module(fallback)
        except ModuleNotFoundError:
            raise exc


def _iter_symbols(payload: object) -> Iterable[str]:
    """
    Iterates over symbols in a payload.

    Args:
        payload (object): The payload to iterate over.

    Returns:
        Iterable[str]: An iterable of symbols.
    """
    if payload is None:
        return []
    if isinstance(payload, dict) and "symbols" in payload:
        return payload.get("symbols") or []
    if isinstance(payload, (list, tuple, set)):
        return payload
    return [str(payload)]


def _fetch_symbols(source: str) -> List[str]:
    """
    Fetches symbols from a source.

    Args:
        source (str): The source to fetch symbols from.

    Returns:
        List[str]: A list of symbols.
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
                result = fn()
            except Exception as exc:
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
    Parses a manual watchlist from an environment variable.

    Returns:
        List[str]: A list of symbols.
    """
    raw = os.getenv("WATCHLIST_TEXT", "") or ""
    if not raw.strip():
        return []
    parts: list[str] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts.extend(chunk.split())
    return parts


def _apply_max_cap(symbols: List[str]) -> List[str]:
    """
    Applies a maximum cap to a list of symbols.

    Args:
        symbols (List[str]): A list of symbols.

    Returns:
        List[str]: A capped list of symbols.
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
    Resolves the watchlist based on the WATCHLIST_SOURCE environment variable.

    Returns:
        Tuple[str, List[str]]: A tuple of (source, symbols).
    """
    requested = (os.getenv("WATCHLIST_SOURCE") or _DEFAULT_SOURCE).strip().lower()
    source = requested or _DEFAULT_SOURCE

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

    symbols = []
    error = None
    start = time.perf_counter()
    try:
        if source == "manual":
            symbols = _parse_manual_from_env()
        else:
            symbols = _fetch_symbols(source)
    except Exception as exc:
        error = str(exc)
        logger.exception("[watchlist:resolve] source=%s error=%s", source, exc)
    duration_ms = (time.perf_counter() - start) * 1000.0

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
    success = not error
    carry = _get_counter(source)
    carry["ok" if success else "error"] += 1
    log_payload = {
        "source": source,
        "count": len(capped),
        "duration_ms": round(duration_ms, 2),
        "ok": success,
    }
    if error:
        log_payload["error"] = error
    logger.info("[watchlist:resolve] %s", log_payload)
    return source, capped


__all__ = ["resolve_watchlist"]
