# app/adapters/storage/__init__.py
"""Lazy export surface for storage adapter."""

__all__ = ["blob_save_json", "blob_load_text", "blob_list", "today_key"]

def __getattr__(name: str):
    if name in __all__:
        from . import azure_blob as _impl  # local import = lazy load
        return getattr(_impl, name)
    raise AttributeError(name)
