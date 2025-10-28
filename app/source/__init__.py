# app/source/__init__.py
"""
Lightweight wrappers exposing watchlist data sources under ``app.source``.

These modules proxy to the existing implementations in ``app.sources`` but
present a simpler interface (`get_symbols`) for higher-level services.
"""

__all__ = ["finviz_source", "textlist_source"]
