from __future__ import annotations

import json
import os
from typing import Any, Dict

from loguru import logger

try:  # Optional dependency until Event Hubs is enabled everywhere
    from azure.eventhub import EventData, EventHubProducerClient
    from azure.identity import DefaultAzureCredential
except Exception:  # pragma: no cover - package may not be installed in some envs
    EventHubProducerClient = None  # type: ignore[assignment]
    EventData = None  # type: ignore[assignment]
    DefaultAzureCredential = None  # type: ignore[assignment]


EH_FQDN = os.getenv("EH_FQDN")


def _is_enabled() -> bool:
    return bool(EH_FQDN and EventHubProducerClient and EventData and DefaultAzureCredential)


def publish_event(hub_env_key: str, payload: Dict[str, Any]) -> None:
    """Publish a JSON event to the configured Event Hub if available."""

    if not _is_enabled():  # Event Hubs disabled or SDK missing
        return

    hub_name = os.getenv(hub_env_key)
    if not hub_name:
        return

    try:
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        producer = EventHubProducerClient(
            fully_qualified_namespace=EH_FQDN,
            eventhub_name=hub_name,
            credential=credential,
        )
        event = EventData(json.dumps(payload, default=str))
        with credential, producer:
            batch = producer.create_batch()
            batch.add(event)
            producer.send_batch(batch)
    except Exception as exc:  # pragma: no cover - log but do not break core flow
        logger.debug("eventhub publish failed hub={} error={}", hub_name, exc)


__all__ = ["publish_event"]
