from __future__ import annotations

import importlib
import os
import re
from typing import Iterable, List

from loguru import logger

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:[.-][A-Z0-9]{1,3})?\b")
_BLACKLIST = {"FOR", "AND", "THE", "ALL", "WITH", "USA", "CEO", "ETF"}


def extract_symbols(raw: str, max_symbols: int = 100) -> List[str]:
    """
    Extract likely stock ticker symbols from a raw text block.

    Accepts comma-, space-, or newline-separated input.
    For example:
        "AAPL, TSLA, NVDA" → ["AAPL", "TSLA", "NVDA"]
    """
    if not raw:
        logger.debug("extract_symbols called with empty input.")
        return []

    raw_clean = raw.replace(",", " ").upper().strip()
    syms = [m.group(0) for m in _TICKER_RE.finditer(raw_clean)]

    out = [s for s in syms if s not in _BLACKLIST]
    out = [s for s in out if 1 <= len(s) <= 5 and s.isalpha()]

    unique = list(dict.fromkeys(out))  # preserve order, dedupe
    logger.info("Extracted {} symbols: {}", len(unique), unique[:10])
    return unique[:max_symbols]


def _load_backend(name: str):
    module_name = f"app.sources.text.{name}_text"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        logger.warning("Textlist backend module missing: {}", module_name)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Textlist backend {} import failed: {}", module_name, exc)
    return None


def _iter_symbols(
    symbols: Iterable[str], *, limit: int | None, seen: set[str]
) -> List[str]:
    out: List[str] = []
    for sym in symbols or []:
        ticker = (sym or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
        if limit is not None and len(out) >= limit:
            break
    return out


def _split_csv(s: str) -> List[str]:
    return [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]


def _env_int(name: str) -> int | None:
    try:
        val = int(os.getenv(name, "").strip())
        return val if val > 0 else None
    except Exception:
        return None


def _from_env_textlist() -> List[str]:
    """
    Fallback loader for env-provided text lists.
    Looks at WATCHLIST_TEXT, then WATCHLIST_MANUAL, then TEXTLIST_EXTRA.
    """
    raw = os.getenv("WATCHLIST_TEXT") or os.getenv("WATCHLIST_MANUAL") or ""
    base = extract_symbols(raw, max_symbols=10_000)
    extras_raw = os.getenv("TEXTLIST_EXTRA", "")
    if extras_raw:
        extras = extract_symbols(extras_raw, max_symbols=10_000)
        base = list(dict.fromkeys([*base, *extras]))
    return base


def get_symbols(*, max_symbols: int | None = None) -> List[str]:
    """
    Aggregate symbols from configured text backends.

    TEXTLIST_BACKENDS="discord,signal"

    By default, if no backends are configured, returns [] to match unit test expectations.
    To enable env-string fallback (WATCHLIST_TEXT / WATCHLIST_MANUAL / TEXTLIST_EXTRA),
    set TEXTLIST_USE_ENV_FALLBACK=1.
    """
    # Resolve effective limit: argument > MAX_WATCHLIST > unlimited
    limit = (
        max_symbols
        if isinstance(max_symbols, int) and max_symbols > 0
        else _env_int("MAX_WATCHLIST")
    )

    backends_raw = os.getenv("TEXTLIST_BACKENDS", "")
    backend_names = [
        name.strip().lower() for name in backends_raw.split(",") if name.strip()
    ]
    use_env_fallback = os.getenv("TEXTLIST_USE_ENV_FALLBACK", "0") == "1"

    # If there are no backends and fallback is not explicitly enabled, return [] (test-friendly).
    if not backend_names and not use_env_fallback:
        return []

    seen: set[str] = set()
    aggregated: List[str] = []

    # Gather from configured backends
    for name in backend_names:
        module = _load_backend(name)
        if module is None:
            continue

        getter = getattr(module, "get_symbols", None)
        if not callable(getter):
            logger.warning("Textlist backend {} missing get_symbols()", name)
            continue

        remaining = None
        if limit is not None:
            remaining = max(limit - len(aggregated), 0)
            if remaining == 0:
                break

        try:
            if remaining is not None:
                symbols = getter(max_symbols=remaining)
            else:
                symbols = getter(max_symbols=None)
        except TypeError:
            try:
                symbols = getter(remaining if remaining is not None else limit)
            except Exception as exc:
                logger.warning("Textlist backend {} get_symbols error: {}", name, exc)
                continue
        except Exception as exc:  # pragma: no cover
            logger.warning("Textlist backend {} get_symbols error: {}", name, exc)
            continue

        aggregated.extend(
            _iter_symbols(
                symbols or [],
                limit=(None if limit is None else max(limit - len(aggregated), 0)),
                seen=seen,
            )
        )
        if limit is not None and len(aggregated) >= limit:
            return aggregated[:limit]

    # Optional env fallback when enabled OR when backends exist but returned nothing and flag is on
    if use_env_fallback and (not aggregated):
        env_syms = _from_env_textlist()
        aggregated.extend(
            _iter_symbols(
                env_syms,
                limit=(None if limit is None else max(limit - len(aggregated), 0)),
                seen=seen,
            )
        )

    if limit is not None and len(aggregated) > limit:
        return aggregated[:limit]
    return aggregated


__all__ = ["extract_symbols", "get_symbols"]
