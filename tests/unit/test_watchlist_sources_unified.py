# tests/unit/test_watchlist_sources_unified.py
import importlib
from typing import List

def _safe_load(path: str):
    module = importlib.import_module(path)
    return getattr(module, "get_symbols")

def test_sources_export_get_symbols():
    # adjust these import paths if your package layout differs
    sources = [
        "app.sources.text.signal_text",
        "app.sources.text.discord_text",
        "app.sources.textlist_source",  # core textlist extractor wrapper
    ]

    for s in sources:
        get_symbols = _safe_load(s)
        assert callable(get_symbols), f"{s}.get_symbols not callable"
        out = get_symbols(max_symbols=5)  # small smoke
        assert isinstance(out, list), f"{s} returned non-list"
        assert all(isinstance(x, str) for x in out), f"{s} returned non-str entries"
