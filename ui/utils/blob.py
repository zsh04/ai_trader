"""Minimal Azure Blob helpers for the Streamlit UI.

These functions intentionally avoid importing the server-side `app` package to
prevent circular imports when the UI runs inside the same process tree.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT", "").strip()
_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY", "").strip()
_DEFAULT_CONTAINER = (
    os.getenv("AZURE_STORAGE_CONTAINER_NAME")
    or os.getenv("AZURE_STORAGE_CONTAINER_DATA")
    or os.getenv("AZURE_STORAGE_CONTAINER", "")
).strip()


@lru_cache(maxsize=1)
def _client():
    try:
        from azure.storage.blob import BlobServiceClient  # type: ignore
    except Exception as exc:  # pragma: no cover - optional in UI
        raise RuntimeError(
            "azure-storage-blob is required for artifact previews"
        ) from exc

    if _CONN_STR:
        return BlobServiceClient.from_connection_string(_CONN_STR)
    if _ACCOUNT and _ACCOUNT_KEY:
        return BlobServiceClient(
            f"https://{_ACCOUNT}.blob.core.windows.net",
            credential=_ACCOUNT_KEY,
        )
    raise RuntimeError(
        "Azure storage not configured for UI (missing connection string or account/key)"
    )


def _split_locator(locator: str) -> Tuple[Optional[str], str]:
    raw = (locator or "").strip().lstrip("/")
    if not raw:
        raise ValueError("blob locator cannot be empty")
    if "/" not in raw:
        return None, raw
    container, path = raw.split("/", 1)
    return (container or None, path)


def blob_load_text(locator: str) -> Optional[str]:
    container, path = _split_locator(locator)
    container_name = container or _DEFAULT_CONTAINER
    if not container_name:
        raise RuntimeError("No container specified for blob load")
    client = _client().get_container_client(container_name)
    blob = client.get_blob_client(path)
    try:
        data = blob.download_blob().readall()
        return data.decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to download blob %s/%s: %s", container_name, path, exc)
        return None


def to_url(locator: str) -> str:
    container, path = _split_locator(locator)
    container_name = container or _DEFAULT_CONTAINER
    account = _ACCOUNT or (_client().account_name if _CONN_STR else None)
    if not account:
        raise RuntimeError("AZURE_STORAGE_ACCOUNT required to build blob URL")
    if not container_name:
        raise RuntimeError("No container specified for URL generation")
    return f"https://{account}.blob.core.windows.net/{container_name}/{path}"


__all__ = ["blob_load_text", "to_url"]
