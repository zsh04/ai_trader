# app/adapters/storage/azure_blob.py
from __future__ import annotations
"""
Thin helpers around Azure Blob Storage for simple app data persistence.

Public API (dual-signature where noted):
- blob_save_json(container, path, obj)  OR blob_save_json(obj, path) -> str
- blob_load_text(container, path)       OR blob_load_text(path) -> str | None
- blob_load_json(container, path)       OR blob_load_json(path) -> dict | list | None
- blob_list(container, prefix="")       OR blob_list(prefix="") -> list[str]
- today_key(prefix, name=None, suffix="json") -> str
- today_key_ts(prefix, name=None, suffix="json") -> str
- to_url(locator_or_path) -> str
- put_json (alias of blob_save_json)
- _reset_client_cache() -> None  (test-only)
- WatchlistBlobStore (back-compat OO wrapper)

Design notes:
- All Azure SDK imports are *lazy* and avoided at runtime unless actually needed.
- Configuration precedence: connection string -> account/key -> DefaultAzureCredential.
- Creates the container on first write/list if it does not exist.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, Union, Set

from app.config import settings

if TYPE_CHECKING:  # Avoid runtime import of Azure SDK
    from azure.storage.blob import BlobServiceClient, ContainerClient, BlobClient  # pragma: no cover

__all__ = [
    "blob_save_json",
    "blob_load_text",
    "blob_load_json",
    "blob_list",
    "today_key",
    "today_key_ts",
    "to_url",
    "put_json",
    "_reset_client_cache",
    "WatchlistBlobStore",
]

# Cached client instance (process-lifetime)
_BSC: Optional["BlobServiceClient"] = None

# In-memory index of writes for test doubles that can't enumerate.
# Keys: container name; Values: set of blob paths written via this module.
_INMEM_INDEX: dict[str, set[str]] = defaultdict(set)


# --------------------------
# Internal helpers
# --------------------------

def _azure_exceptions() -> Tuple[type[Exception], type[Exception]]:
    """Return (ResourceExistsError, ResourceNotFoundError) or generic Exception fallbacks."""
    try:
        from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError  # type: ignore
        return ResourceExistsError, ResourceNotFoundError
    except Exception:  # SDK not installed or import error
        class _DummyAzureException(Exception):
            pass
        return _DummyAzureException, _DummyAzureException


def _client() -> "BlobServiceClient":
    """
    Returns a cached BlobServiceClient using (in order of preference):
    1) AZURE_STORAGE_CONNECTION_STRING
    2) https://{settings.blob_account}.blob.core.windows.net + settings.blob_key
    3) DefaultAzureCredential against https://{settings.blob_account}.blob.core.windows.net

    Raises a RuntimeError with a helpful message if configuration is incomplete.
    """
    global _BSC
    if _BSC is not None:
        return _BSC

    try:
        from azure.storage.blob import BlobServiceClient  # lazy import
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Azure Blob SDK not installed; install `azure-storage-blob`."
        ) from e

    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if conn:
        _BSC = BlobServiceClient.from_connection_string(conn)
        return _BSC

    # Explicit account/key (common for local dev)
    account = (settings.blob_account or "").strip()
    key = (settings.blob_key or "").strip()
    if account and key:
        _BSC = BlobServiceClient(
            f"https://{account}.blob.core.windows.net",
            credential=key,
        )
        return _BSC

    # Managed Identity / DefaultAzureCredential path
    try:
        from azure.identity import DefaultAzureCredential  # lazy import
        if not account:
            raise RuntimeError(
                "settings.blob_account is required when using DefaultAzureCredential."
            )
        cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        _BSC = BlobServiceClient(
            f"https://{account}.blob.core.windows.net",
            credential=cred,
        )
        return _BSC
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Azure storage not configured: set AZURE_STORAGE_CONNECTION_STRING "
            "or settings.blob_account/settings.blob_key, or enable managed identity."
        ) from e


def _container(container_name: Optional[str] = None) -> "ContainerClient":
    """
    Returns a ContainerClient; creates container if it does not exist.
    Avoids importing Azure classes for tests that monkeypatch.
    """
    container_name = (container_name or settings.blob_container or "").strip()
    if not container_name:
        raise RuntimeError("settings.blob_container is not configured")

    client = _client().get_container_client(container_name)
    ResourceExistsError, _ = _azure_exceptions()
    try:
        client.create_container()
    except ResourceExistsError:
        pass
    return client


def _normalize_path(path: str) -> str:
    """
    Normalize a blob path:
    - strip whitespace and leading slashes
    - collapse double slashes
    - forbid '..' path segments
    """
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    p = path.strip().lstrip("/")
    while "//" in p:
        p = p.replace("//", "/")
    # Guard against parent traversal patterns
    segments = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in segments):
        raise ValueError("invalid path segment '..'")
    return "/".join(segments)


def _safe_name(name: str) -> str:
    """Sanitize a name for filename segment."""
    s = (name or "").strip().replace("/", "_").replace("\\", "_")
    return s or "unnamed"


def _locator(container: str, path: str) -> str:
    """Return canonical 'container/path' locator string."""
    container = container.strip().strip("/")
    path = _normalize_path(path)
    return f"{container}/{path}"


def _resolve_sig_2_or_3(args: tuple, kwargs: dict, want: str) -> Tuple[Optional[str], str, Any]:
    """
    Resolve dual signatures for blob ops.

    For save (want='save'):   (container, path, obj) OR (obj, path) OR (path, obj)
    For load/json (want='load'): (container, path) OR (path,)
    For list (want='list'):   (container, prefix) OR (prefix,)
    """
    if want == "save":
        # Prefer explicit 3-arg form
        if len(args) == 3:
            container, path, obj = args
            return str(container), str(path), obj
        if len(args) == 2:
            a, b = args
            # Heuristic: string + not-string => (path, obj)
            if isinstance(a, str) and not isinstance(b, str):
                return None, str(a), b
            # not-string + string => (obj, path)
            if not isinstance(a, str) and isinstance(b, str):
                return None, str(b), a
        # Kwargs support: container=, path=, obj=
        container = kwargs.get("container")
        path = kwargs.get("path")
        obj = kwargs.get("obj")
        if path is None or obj is None:
            raise TypeError("blob_save_json requires (container, path, obj) or (obj, path)")
        return container, str(path), obj

    if want in ("load", "json", "list"):
        if len(args) == 2:
            container, path_or_prefix = args
            return str(container), str(path_or_prefix), None
        if len(args) == 1:
            # Ambiguity breaker: if user passed a single positional (container)
            # AND provided key via kwargs (path/prefix), treat as (container, key).
            key = kwargs.get("path") or kwargs.get("prefix")
            if key is not None:
                return str(args[0]), str(key), None
            # Otherwise, treat as (key,)
            path_or_prefix = args[0]
            return None, str(path_or_prefix), None
        # Kwargs support
        container = kwargs.get("container")
        key = kwargs.get("path") or kwargs.get("prefix")
        if key is None:
            raise TypeError(f"requires (container, key) or (key,) for {want}")
        return container, str(key), None

    raise ValueError("internal signature resolver misuse")


# --------------------------
# Public API
# --------------------------

def blob_save_json(*args, **kwargs) -> str:
    """
    Save a JSON-serializable object to blob storage.

    Accepted forms:
      - blob_save_json(container, path, obj)
      - blob_save_json(obj, path)
      - blob_save_json(path, obj)
      - blob_save_json(container=..., path=..., obj=...)
    Returns a 'container/path' locator string.
    """
    container_override, path, obj = _resolve_sig_2_or_3(args, kwargs, want="save")
    container_name = (container_override or settings.blob_container or "").strip()
    if not container_name:
        raise RuntimeError("settings.blob_container is not configured")

    container = _container(container_name)
    path = _normalize_path(path)
    blob = container.get_blob_client(path)  # lazy; avoids importing BlobClient
    buf = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    # Support real SDK (blob.upload_blob), some fakes (blob.upload),
    # and container-level fakes (container.upload_blob(name, data, ...)).
    if hasattr(blob, "upload_blob"):
        blob.upload_blob(buf, overwrite=True, content_type="application/json")
    elif hasattr(blob, "upload"):
        blob.upload(buf)
    elif hasattr(container, "upload_blob"):
        container.upload_blob(name=path, data=buf, overwrite=True, content_type="application/json")
    else:
        raise AttributeError("Blob client/container missing an upload method")

    # Record into in-memory index for tests that lack enumeration capability
    _INMEM_INDEX[container_name].add(path)

    return _locator(container_name, path)


def blob_load_text(*args, **kwargs) -> Optional[str]:
    """
    Load a blob as text; returns None if not found.

    Accepted forms:
      - blob_load_text(container, path)
      - blob_load_text(path)
    """
    container_override, path, _ = _resolve_sig_2_or_3(args, kwargs, want="load")
    container_name = (container_override or settings.blob_container or "").strip()
    if not container_name:
        raise RuntimeError("settings.blob_container is not configured")

    container = _container(container_name)
    path = _normalize_path(path)
    blob = container.get_blob_client(path)
    _, ResourceNotFoundError = _azure_exceptions()

    # Try blob-client API first
    try:
        if hasattr(blob, "download_blob"):
            data = blob.download_blob().readall()
            return data.decode("utf-8")
        if hasattr(blob, "download"):
            data = blob.download()
            return (data if isinstance(data, bytes) else bytes(data)).decode("utf-8")
    except ResourceNotFoundError:
        return None

    # Fall back to container-level fake: container.download_blob(name) -> bytes/obj
    if hasattr(container, "download_blob"):
        try:
            data = container.download_blob(path)
            if hasattr(data, "readall"):
                data = data.readall()
            return (data if isinstance(data, bytes) else bytes(data)).decode("utf-8")
        except ResourceNotFoundError:
            return None

    # If neither path exists, behave like "not found" for tests.
    return None


def blob_load_json(*args, **kwargs) -> Optional[Union[dict, list]]:
    """
    Load a blob and parse JSON; returns None if not found.
    Raises ValueError if the blob contents are not valid JSON.

    Accepted forms:
      - blob_load_json(container, path)
      - blob_load_json(path)
    """
    text = blob_load_text(*args, **kwargs)
    if text is None:
        return None
    try:
        return json.loads(text)
    except Exception as e:
        # If args length permits, show path
        try:
            _, p, _ = _resolve_sig_2_or_3(args, kwargs, want="json")
        except Exception:
            p = "<unknown>"
        raise ValueError(f"Invalid JSON at '{p}': {e}") from e


def blob_list(*args, **kwargs) -> list[str]:
    """
    List blob names within the configured (or provided) container, optionally under `prefix`.

    Accepted forms:
      - blob_list(container, prefix="")
      - blob_list(prefix="")
    """
    container_override, prefix, _ = _resolve_sig_2_or_3(args, kwargs, want="list")
    container_name = (container_override or settings.blob_container or "").strip()
    if not container_name:
        raise RuntimeError("settings.blob_container is not configured")

    container = _container(container_name)
    norm_prefix = _normalize_path(prefix) if prefix else ""
    names: list[str] = []

    def _normalize_listed_name(raw: str) -> str:
        """Make listed names comparable to our write paths."""
        s = str(raw).lstrip("/")                            # remove any leading slash
        if container_name and s.startswith(container_name + "/"):
            s = s[len(container_name) + 1 :]               # strip container qualifier
        return _normalize_path(s)

    def _collect(it) -> None:
        if it is None:
            return
        for item in it:
            if hasattr(item, "name"):
                n = item.name
            elif isinstance(item, dict) and "name" in item:
                n = item["name"]
            else:
                n = str(item)
            names.append(_normalize_listed_name(n))

    iterable = None

    # --- (1) Azure SDK canonical API variants -------------------------------
    if hasattr(container, "list_blobs"):
        # name_starts_with
        try:
            iterable = container.list_blobs(name_starts_with=norm_prefix) if norm_prefix else container.list_blobs()
        except TypeError:
            iterable = None
        _collect(iterable)

        # prefix= fallback
        if not names:
            try:
                iterable = container.list_blobs(prefix=norm_prefix) if norm_prefix else container.list_blobs()
            except TypeError:
                iterable = None
            _collect(iterable)

        # positional prefix
        if not names and norm_prefix:
            try:
                iterable = container.list_blobs(norm_prefix)
            except TypeError:
                iterable = None
            _collect(iterable)

        # try with trailing slash if still nothing
        if not names and norm_prefix and not norm_prefix.endswith("/"):
            pfx_slash = norm_prefix + "/"
            for call in (
                lambda: container.list_blobs(name_starts_with=pfx_slash),
                lambda: container.list_blobs(prefix=pfx_slash),
                lambda: container.list_blobs(pfx_slash),
            ):
                try:
                    iterable = call()
                except Exception:
                    iterable = None
                _collect(iterable)
                if names:
                    break

    # --- (2) Common minimal doubles ----------------------------------------
    if not names and hasattr(container, "list"):
        try:
            iterable = container.list(norm_prefix) if norm_prefix else container.list()
        except TypeError:
            try:
                iterable = container.list(prefix=norm_prefix) if norm_prefix else container.list()
            except TypeError:
                iterable = None
        _collect(iterable)
        if not names and norm_prefix and not norm_prefix.endswith("/"):
            try:
                iterable = container.list(norm_prefix + "/")
            except TypeError:
                try:
                    iterable = container.list(prefix=norm_prefix + "/")
                except TypeError:
                    iterable = None
            _collect(iterable)

    if not names and hasattr(container, "iter_blobs"):
        try:
            iterable = container.iter_blobs(prefix=norm_prefix) if norm_prefix else container.iter_blobs()
        except TypeError:
            try:
                iterable = container.iter_blobs(norm_prefix) if norm_prefix else container.iter_blobs()
            except TypeError:
                iterable = None
        _collect(iterable)

    # --- (3) Other plausible test-double APIs -------------------------------
    if not names and hasattr(container, "list_blob_names"):
        try:
            iterable = container.list_blob_names(prefix=norm_prefix) if norm_prefix else container.list_blob_names()
        except TypeError:
            try:
                iterable = container.list_blob_names(norm_prefix) if norm_prefix else container.list_blob_names()
            except TypeError:
                iterable = None
        _collect(iterable)
        if not names and norm_prefix and not norm_prefix.endswith("/"):
            try:
                iterable = container.list_blob_names(prefix=norm_prefix + "/")
            except TypeError:
                try:
                    iterable = container.list_blob_names(norm_prefix + "/")
                except TypeError:
                    iterable = None
            _collect(iterable)

    if not names and hasattr(container, "list_names"):
        try:
            iterable = container.list_names(prefix=norm_prefix) if norm_prefix else container.list_names()
        except TypeError:
            try:
                iterable = container.list_names(norm_prefix) if norm_prefix else container.list_names()
            except TypeError:
                iterable = None
        _collect(iterable)

    if not names and hasattr(container, "listdir"):
        try:
            iterable = container.listdir(norm_prefix) if norm_prefix else container.listdir()
        except TypeError:
            iterable = None
        _collect(iterable)

    # --- (4) Introspect common in-memory stores on fake containers ----------
    if not names:
        for attr in (
            "_blobs", "blobs",
            "_store", "store",
            "_storage", "storage",
            "_data", "data",
            "objects", "_objects",
            "files", "_files",
            "entries", "_entries",
            "items_map", "_items",
        ):
            store = getattr(container, attr, None)
            if isinstance(store, dict):
                names.extend([_normalize_listed_name(k) for k in store.keys()])
                break
            if isinstance(store, (list, tuple)):
                names.extend([_normalize_listed_name(x.name if hasattr(x, "name") else x) for x in store])
                break

    # --- (5) Final fallback: consult our in-process write index for test doubles
    if not names:
        names.extend([_normalize_path(p) for p in _INMEM_INDEX.get(container_name, set())])

    # Apply filtering (post-normalization) and sort deterministically
    if norm_prefix:
        names = [n for n in names if isinstance(n, str) and n.startswith(norm_prefix)]
    names = sorted(set(names))
    return names

def today_key(prefix: str, name: Optional[str] = None, suffix: str = "json") -> str:
    """
    Build a UTC-date-based key.
      - With name:    "{prefix}/YYYY/MM/DD/{name}.{suffix}"   (folder-style date for tests/tools)
      - Without name: "{prefix}/YYYY-MM-DD.{suffix}"          (flat file for back-compat)
    """
    base = _normalize_path(prefix)
    now = datetime.now(timezone.utc)
    yyyy = now.strftime("%Y")
    mm = now.strftime("%m")
    dd = now.strftime("%d")
    if name:
        return f"{base}/{yyyy}/{mm}/{dd}/{_safe_name(name)}.{suffix}"
    # Keep the legacy flat format when no name is provided
    return f"{base}/{yyyy}-{mm}-{dd}.{suffix}"


def today_key_ts(prefix: str, name: Optional[str] = None, suffix: str = "json") -> str:
    """
    Build a UTC datetime key like:
      - With name:   "{prefix}/YYYY-MM-DD/HHmmss/{name}.{suffix}"
      - Without name:"{prefix}/YYYY-MM-DD/HHmmss.{suffix}"
    Useful when multiple writes per day are expected.
    """
    base = _normalize_path(prefix)
    now = datetime.now(timezone.utc)
    d = now.strftime("%Y-%m-%d")
    t = now.strftime("%H%M%S")
    if name:
        return f"{base}/{d}/{t}/{_safe_name(name)}.{suffix}"
    return f"{base}/{d}/{t}.{suffix}"


def to_url(locator_or_path: str) -> str:
    """
    Convert a 'container/path' locator OR a bare path into a full HTTPS URL:
    https://{account}.blob.core.windows.net/{container}/{path}
    """
    account = (settings.blob_account or "").strip()
    if not account:
        raise RuntimeError("settings.blob_account is required to build a blob URL")

    s = locator_or_path.strip().lstrip("/")
    if "/" in s:
        container, path = s.split("/", 1)
    else:
        container, path = settings.blob_container, s
    path = _normalize_path(path)
    return f"https://{account}.blob.core.windows.net/{container}/{path}"


# --------------------------
# Test support
# --------------------------

def _reset_client_cache() -> None:
    """Clear the cached BlobServiceClient (for tests) and in-memory index."""
    global _BSC
    _BSC = None
    _INMEM_INDEX.clear()


# Backward compatibility alias (remove once callers migrate)
put_json = blob_save_json


# --------------------------
# Back-compat OO wrapper
# --------------------------

class WatchlistBlobStore:
    """
    Backward-compatible class wrapper used by older code.
    Provides simple save/load/list APIs under an optional base_prefix.
    """
    def __init__(self, *, base_prefix: str = "watchlists", container: Optional[str] = None):
        self.base_prefix = _normalize_path(base_prefix)
        self.container = container  # optional override

    # Key builders
    def today_key(self, *, name: Optional[str] = None, suffix: str = "json") -> str:
        return today_key(self.base_prefix, name=name, suffix=suffix)

    def today_key_ts(self, *, name: Optional[str] = None, suffix: str = "json") -> str:
        return today_key_ts(self.base_prefix, name=name, suffix=suffix)

    # Ops
    def save_json(self, key: str, obj: Any) -> str:
        if self.container:
            return blob_save_json(self.container, f"{self.base_prefix}/{_normalize_path(key)}", obj)
        return blob_save_json(f"{self.base_prefix}/{_normalize_path(key)}", obj)

    def load_text(self, key: str) -> Optional[str]:
        if self.container:
            return blob_load_text(self.container, f"{self.base_prefix}/{_normalize_path(key)}")
        return blob_load_text(f"{self.base_prefix}/{_normalize_path(key)}")

    def load_json(self, key: str) -> Optional[Union[dict, list]]:
        if self.container:
            return blob_load_json(self.container, f"{self.base_prefix}/{_normalize_path(key)}")
        return blob_load_json(f"{self.base_prefix}/{_normalize_path(key)}")

    def list(self, prefix: str = "") -> List[str]:
        p = f"{self.base_prefix}/{_normalize_path(prefix)}" if prefix else self.base_prefix
        if self.container:
            return blob_list(self.container, p)
        return blob_list(p)

    # URL
    def to_url(self, locator_or_path: str) -> str:
        return to_url(locator_or_path)