from __future__ import annotations

import importlib
import logging
import os
import re
from typing import Iterable, List

log = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:[.-][A-Z0-9]{1,3})?\b")
_BLACKLIST = {"FOR", "AND", "THE", "ALL", "WITH", "USA", "CEO", "ETF"}


def extract_symbols(raw: str, max_symbols: int = 100) -> List[str]:
    """
    Extract likely stock ticker symbols from a raw text block.

    Accepts comma-, space-, or newline-separated input.
    For example:
        "AAPL, TSLA, NVDA" → ["AAPL", "TSLA", "NVDA"]

    Parameters
    ----------
    raw : str
        Free-form text containing uppercase words or ticker-like tokens.
    max_symbols : int, optional
        Maximum number of tickers to return (default: 100).

    Returns
    -------
    list[str]
        A list of cleaned, uppercase ticker symbols.
    """
    if not raw:
        log.debug("extract_symbols called with empty input.")
        return []

    raw_clean = raw.replace(",", " ").upper().strip()
    syms = [m.group(0) for m in _TICKER_RE.finditer(raw_clean)]

    out = [s for s in syms if s not in _BLACKLIST]
    out = [s for s in out if 1 <= len(s) <= 5 and s.isalpha()]

    unique = list(dict.fromkeys(out))  # preserve order, dedupe
    log.info("Extracted %d symbols: %s", len(unique), unique[:10])
    return unique[:max_symbols]


def _load_backend(name: str):
    module_name = f"app.sources.text.{name}_text"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        log.warning("Textlist backend module missing: %s", module_name)
    except Exception as exc:  # pragma: no cover - defensive logging
        log.warning("Textlist backend %s import failed: %s", module_name, exc)
    return None


def _iter_symbols(symbols: Iterable[str], *, limit: int | None, seen: set[str]) -> List[str]:
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


def get_symbols(*, max_symbols: int | None = None) -> List[str]:
    """
    Aggregate symbols from configured text backends.

    TEXTLIST_BACKENDS="discord,signal"
    """
    backends_raw = os.getenv("TEXTLIST_BACKENDS", "")
    backend_names = [name.strip().lower() for name in backends_raw.split(",") if name.strip()]
    if not backend_names:
        return []

    limit = max_symbols if isinstance(max_symbols, int) and max_symbols > 0 else None
    seen: set[str] = set()
    aggregated: List[str] = []

    for name in backend_names:
        module = _load_backend(name)
        if module is None:
            continue

        getter = getattr(module, "get_symbols", None)
        if not callable(getter):
            log.warning("Textlist backend %s missing get_symbols()", name)
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
                symbols = getter(remaining if remaining is not None else max_symbols)
            except Exception as exc:
                log.warning("Textlist backend %s get_symbols error: %s", name, exc)
                continue
        except Exception as exc:  # pragma: no cover - defensive logging
            log.warning("Textlist backend %s get_symbols error: %s", name, exc)
            continue

        aggregated.extend(_iter_symbols(symbols or [], limit=None if limit is None else max(limit - len(aggregated), 0), seen=seen))
        if limit is not None and len(aggregated) >= limit:
            return aggregated[:limit]

    if limit is not None and len(aggregated) > limit:
        return aggregated[:limit]
    return aggregated


__all__ = ["extract_symbols", "get_symbols"]
