from __future__ import annotations

import importlib
import logging
import os
import re
from typing import Iterable, List, Optional

log = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"\b[A-Z0-9]{1,7}(?:[.-][A-Z0-9]{1,6})?\b")
_BLACKLIST = {"FOR", "AND", "THE", "ALL", "WITH", "USA", "CEO", "ETF"}

# Final stricter validation (allow letters, digits, dot, dash; 1-7 chars plus optional compound parts)
_VALID_TICKER_FINAL_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9\.-]{0,6})$")


def extract_symbols(raw: str, max_symbols: int = 100) -> List[str]:
    """
    Extract likely stock ticker symbols from a raw text block.

    Accepts comma-, space-, or newline-separated input.
    For example:
        "AAPL, TSLA, NVDA" → ["AAPL", "TSLA", "NVDA"]
    """
    if not raw:
        log.debug("extract_symbols called with empty input.")
        return []

    raw_clean = raw.replace(",", " ").upper().strip()
    syms = [m.group(0) for m in _TICKER_RE.finditer(raw_clean)]

    # Remove explicit blacklisted tokens
    out = [s for s in syms if s not in _BLACKLIST]

    # Final validation — allow alphanumeric and '.' or '-' characters
    out = [s for s in out if _VALID_TICKER_FINAL_RE.fullmatch(s)]

    # Preserve order and dedupe
    unique = list(dict.fromkeys(out))
    # Keep detailed listing to debug only; keep count at info level
    log.debug("Extracted %d symbols: %s", len(unique), unique[:50])
    log.info("Extracted %d symbols", len(unique))
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


def _iter_symbols(symbols: Iterable[str], *, limit: Optional[int], seen: set[str]) -> List[str]:
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


def _env_int(name: str) -> Optional[int]:
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


def get_symbols(*, max_symbols: Optional[int] = None) -> List[str]:
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
    backend_names = [name.strip().lower() for name in backends_raw.split(",") if name.strip()]
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
            log.warning("Textlist backend %s missing get_symbols()", name)
            continue

        remaining: Optional[int] = None
        if limit is not None:
            remaining = max(limit - len(aggregated), 0)
            if remaining == 0:
                break

        # Prefer keyword invocation but fallback to positional where necessary
        try:
            symbols = getter(max_symbols=remaining)
        except TypeError:
            try:
                symbols = getter(remaining)
            except Exception as exc:
                log.warning("Textlist backend %s get_symbols error: %s", name, exc)
                continue
        except Exception as exc:  # pragma: no cover
            log.warning("Textlist backend %s get_symbols error: %s", name, exc)
            continue

        aggregated.extend(
            _iter_symbols(
                symbols or [],
                limit=None if limit is None else max(limit - len(aggregated), 0),
                seen=seen,
            )
        )
        if limit is not None and len(aggregated) >= limit:
            return aggregated[:limit]

    # Optional env fallback when enabled — use it to fill up to the limit (not only when empty)
    if use_env_fallback and (limit is None or len(aggregated) < limit):
        env_syms = _from_env_textlist()
        aggregated.extend(
            _iter_symbols(
                env_syms,
                limit=None if limit is None else max(limit - len(aggregated), 0),
                seen=seen,
            )
        )

    if limit is not None and len(aggregated) > limit:
        return aggregated[:limit]
    return aggregated


__all__ = ["extract_symbols", "get_symbols"]