# app/data/store.py
import os, json
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