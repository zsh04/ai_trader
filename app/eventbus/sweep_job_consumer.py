from __future__ import annotations

import json
import os
import signal
from contextlib import suppress
from datetime import datetime, timezone
from typing import Dict, Optional

try:
    from azure.eventhub import EventData, EventHubConsumerClient
    from azure.eventhub.extensions.checkpointstoreblob import BlobCheckpointStore
except Exception:  # pragma: no cover
    EventHubConsumerClient = None  # type: ignore
    EventData = object  # type: ignore
    BlobCheckpointStore = None  # type: ignore

try:
    import requests
    from azure.identity import AzureCliCredential, DefaultAzureCredential
except Exception:  # pragma: no cover
    DefaultAzureCredential = AzureCliCredential = None  # type: ignore
    requests = None  # type: ignore

from loguru import logger

from app.backtest import sweep_registry

MANAGEMENT_SCOPE = "https://management.azure.com/.default"
API_VERSION = os.getenv("AZURE_JOBS_API_VERSION", "2024-03-01")


def _make_credential(use_cli: bool = False):
    if DefaultAzureCredential is None or AzureCliCredential is None:
        raise RuntimeError("azure.identity is required for sweep job consumer")
    return (
        AzureCliCredential()
        if use_cli
        else DefaultAzureCredential(exclude_shared_token_cache_credential=True)
    )


def _build_env(payload: Dict[str, object]) -> list[Dict[str, str]]:
    job_id = str(payload.get("job_id") or f"event-{int(datetime.now().timestamp())}")
    config_path = str(payload.get("config_path") or payload.get("config"))
    env_vars = [
        {"name": "SWEEP_JOB_ID", "value": job_id},
    ]
    if config_path.startswith("blob://"):
        env_vars.append({"name": "SWEEP_CONFIG_BLOB", "value": config_path})
        env_vars.append(
            {
                "name": "SWEEP_CONFIG_PATH",
                "value": f"/workspace/configs/{job_id}.yaml",
            }
        )
    else:
        env_vars.append({"name": "SWEEP_CONFIG_PATH", "value": config_path})
    for extra_key in ("strategy", "symbol", "mode"):
        if payload.get(extra_key):
            env_vars.append(
                {
                    "name": f"SWEEP_META_{extra_key.upper()}",
                    "value": str(payload[extra_key]),
                }
            )
    return env_vars


class ContainerAppJobClient:
    def __init__(self, *, resource_id: str, container_name: str, credential) -> None:
        self.resource_id = resource_id.strip("/")
        self.container_name = container_name
        self.credential = credential

    def start(self, env_vars: list[Dict[str, str]]) -> None:
        if requests is None:
            raise RuntimeError("requests package missing")
        token = self.credential.get_token(MANAGEMENT_SCOPE)
        url = f"https://management.azure.com/{self.resource_id}/start?api-version={API_VERSION}"
        body = {
            "template": {
                "containers": [
                    {
                        "name": self.container_name,
                        "env": env_vars,
                    }
                ]
            }
        }
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        if response.status_code not in (200, 202):
            raise RuntimeError(
                f"job start failed status={response.status_code} body={response.text}"
            )


class SweepJobEventConsumer:
    def __init__(
        self,
        *,
        namespace: str,
        hub: str,
        consumer_group: str,
        job_resource_id: str,
        job_container_name: str = "sweep-job",
        storage_account: Optional[str] = None,
        checkpoint_container: Optional[str] = None,
        use_cli_auth: bool = False,
    ) -> None:
        if EventHubConsumerClient is None:
            raise RuntimeError("azure-eventhub is required")
        self.namespace = namespace
        self.hub = hub
        self.consumer_group = consumer_group
        self.storage_account = storage_account
        self.checkpoint_container = checkpoint_container
        self.credential = _make_credential(use_cli_auth)
        self._store = None
        self._client = None
        self.job_client = ContainerAppJobClient(
            resource_id=job_resource_id,
            container_name=job_container_name,
            credential=self.credential,
        )

    def _checkpoint_store(self):
        if not self.storage_account or not self.checkpoint_container:
            return None
        return BlobCheckpointStore(
            blob_account_url=f"https://{self.storage_account}.blob.core.windows.net",
            container_name=self.checkpoint_container,
            credential=self.credential,
        )

    def _on_event(self, partition_context, event: EventData) -> None:
        try:
            payload = json.loads(event.body_as_str())
        except json.JSONDecodeError:
            logger.warning("[sweep-consumer] invalid payload: %s", event.body_as_str())
            return
        env_vars = _build_env(payload)
        job_id = next(
            (env["value"] for env in env_vars if env["name"] == "SWEEP_JOB_ID"),
            "unknown",
        )
        try:
            self.job_client.start(env_vars)
            logger.info("[sweep-consumer] started job=%s", job_id)
            sweep_registry.record_job_event(
                job_id,
                "dispatched",
                dispatched_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            logger.exception("[sweep-consumer] failed starting job %s: %s", job_id, exc)
            sweep_registry.record_job_event(
                job_id,
                "failed",
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        if partition_context and self._store:
            partition_context.update_checkpoint(event)

    def run(self) -> None:
        store = self._checkpoint_store()
        client = EventHubConsumerClient(
            fully_qualified_namespace=self.namespace,
            eventhub_name=self.hub,
            consumer_group=self.consumer_group,
            credential=self.credential,
            checkpoint_store=store,
        )
        self._client = client
        self._store = store
        stop = False

        def _stop(*_args):
            nonlocal stop
            stop = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            with suppress(Exception):
                signal.signal(sig, _stop)

        with client:
            while not stop:
                client.receive(
                    on_event=self._on_event,
                    starting_position="@latest",
                    max_wait_time=5,
                )


__all__ = ["SweepJobEventConsumer"]
