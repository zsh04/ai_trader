# app/source/textlist_source.py
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from app.sources.textlist_source import extract_symbols

__all__ = ["get_symbols"]

_ENV_KEYS = ("WATCHLIST_TEXTLIST", "WATCHLIST_TEXT")


def _load_text_payload(path: Optional[str] = None) -> str:
    """
    Load raw watchlist text from environment or a file path.

    Order of precedence:
      1. ``path`` argument (if provided).
      2. Environment variables in ``_ENV_KEYS``.
      3. Environment variable ``WATCHLIST_TEXTLIST_FILE`` pointing to a file.
    """
    if path:
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            return ""

    for key in _ENV_KEYS:
        value = os.getenv(key, "")
        if value:
            return value

    file_path = os.getenv("WATCHLIST_TEXTLIST_FILE")
    if not file_path:
        return ""
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return ""


def get_symbols(
    text: Optional[str] = None,
    *,
    max_symbols: int = 100,
    path: Optional[str] = None,
) -> List[str]:
    """
    Parse a raw text blob into ticker symbols using ``extract_symbols``.

    Args:
        text: Optional raw text; if omitted we inspect environment/file sources.
        max_symbols: Maximum number of symbols to return.
        path: Optional file path override for loading the text payload.
    """
    raw = text if text is not None else _load_text_payload(path=path)
    if not raw:
        return []
    return extract_symbols(raw, max_symbols=max_symbols)
