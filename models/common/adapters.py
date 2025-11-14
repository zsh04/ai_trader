from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Tuple

from .blob_client import AdapterBlobClient

logger = logging.getLogger(__name__)


@dataclass
class AdapterResult:
    effective_tag: str
    source: str
    metadata: dict


def _parse_blob_url(url: Optional[str], default_container: str) -> Tuple[str, str]:
    if not url:
        return default_container, ""
    if "//" in url:
        _, remainder = url.split("//", 1)
    else:
        remainder = url
    remainder = remainder.strip("/")
    parts = remainder.split("/", 1)
    container = parts[0] or default_container
    prefix = parts[1] if len(parts) > 1 else ""
    return container, prefix


def ensure_cache_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root


def maybe_apply_adapter(
    *,
    service: str,
    desired_tag: Optional[str],
    baked_tag: str,
    storage_account: Optional[str],
    adapters_url: Optional[str],
    cache_dir: Path,
    apply_callback: Callable[[Path], None],
) -> AdapterResult:
    """Download + apply adapter if desired tag differs from baked."""

    effective = baked_tag
    metadata: dict = {"source": "baked"}
    ensure_cache_dir(cache_dir)

    if not desired_tag or desired_tag == baked_tag:
        logger.info("[adapter] using baked tag=%s for service=%s", baked_tag, service)
        return AdapterResult(effective_tag=baked_tag, source="baked", metadata=metadata)

    if not storage_account:
        logger.warning("[adapter] storage account missing; falling back to baked adapter")
        return AdapterResult(effective_tag=baked_tag, source="baked", metadata=metadata)

    container, prefix = _parse_blob_url(adapters_url, "adapters")
    client = AdapterBlobClient(
        storage_account=storage_account,
        container=container,
        prefix=prefix,
    )
    blob_path = f"{service}/{desired_tag}/adapter.tar.gz"
    target = cache_dir / service / desired_tag / "adapter.tar.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    downloaded = client.download(blob_path, target)
    if not downloaded:
        return AdapterResult(effective_tag=baked_tag, source="baked", metadata=metadata)

    apply_callback(target)
    meta = client.download_json(f"{service}/{desired_tag}/metadata.json") or {}
    meta.setdefault("applied_at", datetime.now(tz=timezone.utc).isoformat())
    logger.info(
        "[adapter] applied runtime adapter service=%s tag=%s blob=%s",
        service,
        desired_tag,
        blob_path,
    )
    return AdapterResult(effective_tag=desired_tag, source="blob", metadata=meta)


def persist_effective_metadata(cache_dir: Path, payload: dict) -> None:
    ensure_cache_dir(cache_dir)
    target = cache_dir / "effective.json"
    target.write_text(json.dumps(payload, indent=2))
    logger.info("[adapter] effective metadata persisted at %s", target)
