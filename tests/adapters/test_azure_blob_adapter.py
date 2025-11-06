# tests/adapters/test_azure_blob_adapter.py
from __future__ import annotations

import json
import re
import sys
import types
from importlib import import_module, reload

import pytest


# -------------------------------
# Fake Azure SDK (blob + core.ex)
# -------------------------------
class _FakeDownloader:
    def __init__(self, data: bytes):
        self._data = data

    def readall(self) -> bytes:
        return self._data

    # some helpers use .content_as_text() on the SDK response
    def content_as_text(self, encoding="utf-8") -> str:
        return self._data.decode(encoding)


class _FakeBlobClient:
    def __init__(self, container: str, name: str):
        self.url = f"https://fake/{container}/{name}"


class _FakeContainerClient:
    def __init__(self):
        self._store: dict[str, bytes] = {}

    def create_container(self):
        return None

    def upload_blob(self, name: str, data, overwrite=False, **kwargs):
        if not overwrite and name in self._store:
            raise Exception("BlobExists")
        if hasattr(data, "read"):
            raw = data.read()
            if isinstance(raw, str):
                raw = raw.encode()
        elif isinstance(data, str):
            raw = data.encode()
        else:
            raw = bytes(data)
        self._store[name] = raw
        return None

    def download_blob(self, name: str) -> _FakeDownloader:
        if name not in self._store:
            raise KeyError(name)
        return _FakeDownloader(self._store[name])

    def list_blobs(self, name_starts_with: str = ""):
        return [
            types.SimpleNamespace(name=k)
            for k in sorted(self._store)
            if k.startswith(name_starts_with)
        ]

    def get_blob_client(self, name: str) -> _FakeBlobClient:
        return _FakeBlobClient("utest", name)


class _FakeBlobServiceClient:
    def __init__(self):
        self._containers: dict[str, _FakeContainerClient] = {}

    @classmethod
    def from_connection_string(cls, *_args, **_kwargs):
        return cls()

    def get_container_client(self, container: str) -> _FakeContainerClient:
        self._containers.setdefault(container, _FakeContainerClient())
        return self._containers[container]


# exceptions shim
class _ResExists(Exception): ...


class _ResNotFound(Exception): ...


@pytest.fixture(autouse=True)
def fake_azure_sdk(monkeypatch):
    # build module tree: azure, azure.storage, azure.storage.blob, azure.core.exceptions, azure.identity
    mod_azure = types.ModuleType("azure")
    mod_storage = types.ModuleType("azure.storage")
    mod_blob = types.ModuleType("azure.storage.blob")
    mod_blob.BlobServiceClient = _FakeBlobServiceClient

    # some code may import ContentSettings; provide a lightweight stub
    class ContentSettings:
        def __init__(self, content_type=None):
            self.content_type = content_type

    mod_blob.ContentSettings = ContentSettings

    mod_core = types.ModuleType("azure.core")
    mod_ex = types.ModuleType("azure.core.exceptions")
    mod_ex.ResourceExistsError = _ResExists
    mod_ex.ResourceNotFoundError = _ResNotFound

    mod_id = types.ModuleType("azure.identity")

    class DefaultAzureCredential: ...

    mod_id.DefaultAzureCredential = DefaultAzureCredential

    sys.modules["azure"] = mod_azure
    sys.modules["azure.storage"] = mod_storage
    sys.modules["azure.storage.blob"] = mod_blob
    sys.modules["azure.core"] = mod_core
    sys.modules["azure.core.exceptions"] = mod_ex
    sys.modules["azure.identity"] = mod_id

    # Ensure code path prefers connection string to avoid DefaultAzureCredential
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")

    # Reload impl after fakes installed
    # Import the concrete implementation (renamed file) and the package re-exports
    impl = import_module("app.adapters.storage.azure_blob")
    reload(impl)
    pkg = import_module("app.adapters.storage")
    reload(pkg)

    yield


def _import_exports():
    # Pull from the public export surface (storage/__init__.py)
    from app.adapters.storage import (
        blob_list,
        blob_load_text,
        blob_save_json,
        today_key,
    )

    return blob_save_json, blob_load_text, blob_list, today_key


def test_roundtrip_save_and_load_text(tmp_path):
    blob_save_json, blob_load_text, _, _ = _import_exports()
    # Use a deterministic key so we don't rely on today_key internals
    container = "utest"
    key = "unit/roundtrip/sample.json"
    payload = {"a": 1, "b": ["x", 2]}
    # Save
    blob_save_json(container, key, payload)
    # Load text and verify JSON
    s = blob_load_text(container, key)
    assert isinstance(s, str)
    assert json.loads(s) == payload


def test_list_blobs_with_prefix():
    blob_save_json, blob_load_text, blob_list, _ = _import_exports()
    container = "utest"
    blob_save_json(container, "pfx/2025/10/30/a.json", {"x": 1})
    blob_save_json(container, "pfx/2025/10/30/b.json", {"x": 2})
    blob_save_json(container, "pfx/2025/11/01/c.json", {"x": 3})

    names = blob_list(container, prefix="pfx/2025/10/30")
    assert names == ["pfx/2025/10/30/a.json", "pfx/2025/10/30/b.json"]


def test_overwrite_true_by_default():
    blob_save_json, blob_load_text, _, _ = _import_exports()
    container = "utest"
    key = "overwrite/check.json"
    blob_save_json(container, key, {"v": 1})
    blob_save_json(container, key, {"v": 2})  # should not raise; should overwrite
    s = blob_load_text(container, key)
    assert json.loads(s) == {"v": 2}


def test_today_key_shape():
    # We assert shape, not exact timestamp, to avoid flakiness across timezones.
    _, _, _, today_key = _import_exports()
    k = today_key(prefix="ingest", name="AAPL", suffix="json")
    # must include a yyyy/mm/dd path component, be string, end with suffix
    assert isinstance(k, str)
    assert re.search(r"\d{4}/\d{2}/\d{2}/", k), k
    assert k.endswith(".json")
    assert "AAPL".lower() in k.lower()
