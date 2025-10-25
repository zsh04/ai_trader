# app/data/store.py
import json
import os
from datetime import datetime, timezone

from azure.storage.blob import BlobServiceClient

from app.config import settings


def _client() -> BlobServiceClient:
    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    if conn:
        return BlobServiceClient.from_connection_string(conn)
    return BlobServiceClient(
        f"https://{settings.blob_account}.blob.core.windows.net",
        credential=settings.blob_key,
    )


def put_json(obj, path: str) -> str:
    bsc = _client()
    container = bsc.get_container_client(settings.blob_container)
    try:
        container.create_container()
    except Exception:
        pass
    blob = container.get_blob_client(path)
    buf = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    blob.upload_blob(buf, overwrite=True, content_type="application/json")
    return f"{settings.blob_container}/{path}"


def today_key(prefix: str, suffix: str = "json") -> str:
    d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{prefix}/{d}.{suffix}"

# app/adapters/storage/blob.py
"""
Thin helpers around Azure Blob Storage for simple app data persistence.

Public API (re-exported via app.adapters.storage.__init__):
- blob_save_json(obj, path) -> str
- blob_load_text(path) -> str | None
- blob_list(prefix="") -> list[str]
- today_key(prefix, suffix="json") -> str

Notes:
- Uses AZURE_STORAGE_CONNECTION_STRING when provided; otherwise falls back
  to account/key from settings.
- Creates the target container on first write if it doesn't exist.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List, Optional

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContainerClient, BlobClient

from app.config import settings

_BSC: Optional[BlobServiceClient] = None


def _client() -> BlobServiceClient:
    """
    Returns a cached BlobServiceClient using either:
    - AZURE_STORAGE_CONNECTION_STRING, or
    - https://{settings.blob_account}.blob.core.windows.net with settings.blob_key
    """
    global _BSC
    if _BSC is not None:
        return _BSC

    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    if conn:
        _BSC = BlobServiceClient.from_connection_string(conn)
        return _BSC

    if not settings.blob_account or not settings.blob_key:
        raise RuntimeError(
            "Azure storage not configured: set AZURE_STORAGE_CONNECTION_STRING "
            "or settings.blob_account/settings.blob_key"
        )
    _BSC = BlobServiceClient(
        f"https://{settings.blob_account}.blob.core.windows.net", credential=settings.blob_key
    )
    return _BSC


def _container() -> ContainerClient:
    """
    Returns a ContainerClient; creates container if it does not exist.
    """
    if not settings.blob_container:
        raise RuntimeError("settings.blob_container is not configured")

    client = _client().get_container_client(settings.blob_container)
    try:
        client.create_container()
    except ResourceExistsError:
        pass
    return client


def blob_save_json(obj, path: str) -> str:
    """
    Save a JSON-serializable object to blob storage at `path`.

    Returns a "container/path" locator string.
    """
    container = _container()
    blob: BlobClient = container.get_blob_client(path)
    buf = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    blob.upload_blob(buf, overwrite=True, content_type="application/json")
    return f"{settings.blob_container}/{path}"


def blob_load_text(path: str) -> Optional[str]:
    """
    Load a blob as text; returns None if not found.
    """
    container = _container()
    blob = container.get_blob_client(path)
    try:
        data = blob.download_blob().readall()
    except ResourceNotFoundError:
        return None
    return data.decode("utf-8")


def blob_list(prefix: str = "") -> List[str]:
    """
    List blob names within the configured container, optionally under `prefix`.
    """
    container = _container()
    names: List[str] = []
    for item in container.list_blobs(name_starts_with=prefix or None):
        names.append(item.name)
    return names


def today_key(prefix: str, suffix: str = "json") -> str:
    """
    Build a UTC-date-based key like: "{prefix}/YYYY-MM-DD.{suffix}"
    """
    d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{prefix}/{d}.{suffix}"


# --- Backward compatibility aliases (can be removed after migration) ---
put_json = blob_save_json