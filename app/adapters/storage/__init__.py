"""Storage adapter export surface — wraps Azure Blob helper functions."""

from .blob import (
    blob_list,
    blob_load_text,
    blob_save_json,
    today_key,
)

__all__ = ["blob_save_json", "blob_load_text", "blob_list", "today_key"]
