#!/usr/bin/env python3
"""Entry point for ACA sweep jobs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Tuple

from loguru import logger

try:  # optional dependency when running locally
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobClient
except Exception:  # pragma: no cover
    DefaultAzureCredential = None  # type: ignore
    BlobClient = None  # type: ignore

from app.backtest import sweeps


def _parse_blob_url(url: str) -> Tuple[str, str]:
    if "//" in url:
        _, remainder = url.split("//", 1)
    else:
        remainder = url
    remainder = remainder.strip("/")
    parts = remainder.split("/", 1)
    container = parts[0]
    blob = parts[1] if len(parts) > 1 else ""
    return container, blob


def _download_config(target: Path) -> None:
    blob_url = os.getenv("SWEEP_CONFIG_BLOB")
    storage_account = os.getenv("STORAGE_ACCOUNT") or os.getenv("STG_ACCOUNT")
    if not blob_url or not storage_account:
        return
    if DefaultAzureCredential is None or BlobClient is None:
        logger.warning("[sweep-job] azure sdk unavailable; cannot fetch config blob")
        return
    container, blob_path = _parse_blob_url(blob_url)
    credential = DefaultAzureCredential(exclude_shared_token_cache_credential=True)
    client = BlobClient(
        account_url=f"https://{storage_account}.blob.core.windows.net",
        container_name=container,
        blob_name=blob_path,
        credential=credential,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        handle.write(client.download_blob().readall())
    logger.info("[sweep-job] downloaded config blob=%s", blob_path)


def main() -> None:
    config_path = os.getenv("SWEEP_CONFIG_PATH")
    if not config_path:
        raise SystemExit("SWEEP_CONFIG_PATH env variable is required")
    output_dir = os.getenv("SWEEP_OUTPUT_DIR")
    job_id = os.getenv("SWEEP_JOB_ID")
    mode = os.getenv("SWEEP_JOB_MODE", "aca")
    path = Path(config_path).expanduser()
    if not path.exists():
        _download_config(path)
    if not path.exists():
        raise SystemExit(f"Sweep config not found: {path}")
    logger.info("[sweep-job] starting config=%s", path)
    result = sweeps.run_sweep(path, job_id=job_id, mode=mode)
    if output_dir:
        out = Path(output_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(result, indent=2, default=str))
    logger.info("[sweep-job] completed dir=%s", result.get("sweep_dir"))


if __name__ == "__main__":
    main()
