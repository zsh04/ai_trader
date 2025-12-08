from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils import env as ENV
from app.utils.azure_storage import BlobStorageClient

logger = logging.getLogger(__name__)


def _run_az_command(args: list[str]) -> str:
    """Run an azure cli command and return stdout."""
    cmd = ["az"] + args
    logger.info("Executing: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def trigger_sweep_job(
    config_path: Path,
    job_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Trigger a remote ACA sweep job.

    1. Reads the local YAML config.
    2. Uploads it to Azure Blob Storage.
    3. Triggers the 'ai-trader-sweep' job in ACA with the blob URL.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    # 1. Prepare Job ID and Config
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    job_ref = job_id or f"sweep-{timestamp}"
    blob_name = f"configs/{job_ref}.yaml"
    config_content = config_path.read_text()

    # 2. Upload Config to Blob
    if dry_run:
        logger.info("[dry-run] Would upload config to %s", blob_name)
        blob_url = f"https://dryrun.blob.core.windows.net/configs/{blob_name}"
    else:
        try:
            client = BlobStorageClient()
            blob_url = client.upload_text(
                container_name="trader-data",  # Storing configs in data container
                blob_name=blob_name,
                data=config_content,
            )
        except Exception as e:
            logger.warning("Blob upload failed (check credentials?): %s", e)
            if ENV.AZURE_STORAGE_CONNECTION_STRING:
                raise
            # Fallback for local testing without storage
            blob_url = f"local://{config_path.name}"

    # 3. Trigger ACA Job
    # We pass the blob URL via env var SWEEP_CONFIG_BLOB
    # The job itself knows how to download from that URL (or sas token if needed, but we assume managed identity)
    
    resource_group = ENV.ACA_RESOURCE_GROUP
    job_name = ENV.ACA_JOB_NAME
    
    if not resource_group or not job_name:
         msg = "ACA_RESOURCE_GROUP and ACA_JOB_NAME must be set in env"
         if dry_run:
             logger.warning(msg)
         else:
             raise ValueError(msg)

    # Prepare env vars for the container
    # Note: 'az containerapp job start' uses --env-vars key=value ...
    env_vars = [
        f"SWEEP_CONFIG_BLOB={blob_url}",
        f"SWEEP_JOB_ID={job_ref}",
        "SWEEP_JOB_MODE=aca",
    ]

    cmd_args = [
        "containerapp",
        "job",
        "start",
        "--name",
        job_name,
        "--resource-group",
        resource_group,
        "--env-vars",
    ] + env_vars

    if dry_run:
        logger.info("[dry-run] Would execute: az %s", " ".join(cmd_args))
        return {"job_id": job_ref, "status": "dry-run", "blob_url": blob_url}

    try:
        output = _run_az_command(cmd_args)
        logger.info("ACA Job triggered successfully: %s", output)
        return {
            "job_id": job_ref,
            "status": "triggered",
            "blob_url": blob_url,
            "provider_output": output,
        }
    except subprocess.CalledProcessError as e:
        logger.error("Failed to trigger ACA job: %s\nStderr: %s", e, e.stderr)
        raise
