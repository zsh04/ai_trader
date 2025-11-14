from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobClient

logger = logging.getLogger(__name__)


class AdapterBlobClient:
    """Helper to fetch adapter artifacts from Azure Blob Storage via Managed Identity."""

    def __init__(
        self, *, storage_account: str, container: str, prefix: str | None = None
    ) -> None:
        self.storage_account = storage_account
        self.container = container
        self.prefix = (prefix or "").strip("/")
        self.credential = DefaultAzureCredential(
            exclude_shared_token_cache_credential=True
        )
        self._endpoint = f"https://{storage_account}.blob.core.windows.net"

    def _resolve_path(self, blob_path: str) -> str:
        blob_path = blob_path.strip("/")
        if self.prefix:
            return f"{self.prefix}/{blob_path}".strip("/")
        return blob_path

    def _blob_client(self, blob_path: str) -> BlobClient:
        return BlobClient(
            account_url=self._endpoint,
            container_name=self.container,
            blob_name=self._resolve_path(blob_path),
            credential=self.credential,
        )

    def download(self, blob_path: str, dest: Path) -> bool:
        client = self._blob_client(blob_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as handle:
                data = client.download_blob().readall()
                handle.write(data)
            logger.info("[blob] downloaded %s to %s", blob_path, dest)
            return True
        except Exception as exc:  # pragma: no cover - network runtime
            if getattr(exc, "status_code", None) == 404:
                logger.warning("[blob] adapter not found at %s", blob_path)
                return False
            logger.error("[blob] failed downloading %s: %s", blob_path, exc)
            raise

    def download_json(self, blob_path: str) -> Optional[dict]:
        try:
            client = self._blob_client(blob_path)
            data = client.download_blob().readall()
            return json.loads(data)
        except Exception:  # pragma: no cover - optional metadata
            return None
