from __future__ import annotations

import logging
from typing import Optional

from azure.storage.blob import BlobServiceClient

from app.utils import env as ENV

logger = logging.getLogger(__name__)


class BlobStorageClient:
    """Wrapper around Azure Blob Storage SDK."""

    def __init__(self, connection_string: Optional[str] = None):
        """Initialize the client with connection string.

        Defaults to ENV.AZURE_STORAGE_CONNECTION_STRING if not provided.
        """
        self.conn_str = connection_string or ENV.AZURE_STORAGE_CONNECTION_STRING
        if not self.conn_str:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not set")
        self.service_client = BlobServiceClient.from_connection_string(self.conn_str)

    def upload_text(
        self, container_name: str, blob_name: str, data: str, overwrite: bool = True
    ) -> str:
        """Upload text data to a blob."""
        try:
            container_client = self.service_client.get_container_client(container_name)
            if not container_client.exists():
                container_client.create_container()

            blob_client = container_client.get_blob_client(blob_name)
            blob_client.upload_blob(data, overwrite=overwrite)
            logger.info(
                "Uploaded blob: container=%s blob=%s bytes=%d",
                container_name,
                blob_name,
                len(data),
            )
            return blob_client.url
        except Exception as e:
            logger.error("Failed to upload blob %s/%s: %s", container_name, blob_name, e)
            raise
