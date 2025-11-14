from __future__ import annotations

import json
import signal
from contextlib import suppress
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

try:  # optional dependency for tests/offline runs
    from azure.eventhub import EventData, EventHubConsumerClient
    from azure.eventhub.extensions.checkpointstoreblob import BlobCheckpointStore
except Exception:  # pragma: no cover - optional
    EventHubConsumerClient = None  # type: ignore
    BlobCheckpointStore = None  # type: ignore
    EventData = object  # type: ignore

try:
    from azure.identity import AzureCliCredential, DefaultAzureCredential
except Exception:  # pragma: no cover
    AzureCliCredential = DefaultAzureCredential = None  # type: ignore

from loguru import logger

from app.adapters.db.postgres import get_session
from app.db.repositories.trading import TradingRepository


def _make_credential(local: bool):
    if AzureCliCredential is None or DefaultAzureCredential is None:
        raise RuntimeError("azure.identity is required to run the order consumer")
    return AzureCliCredential() if local else DefaultAzureCredential()


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def intent_to_order_record(intent: Dict[str, object]) -> Dict[str, object]:
    run_id = intent.get("run_id") or uuid4().hex
    submitted_at = _parse_timestamp(intent.get("timestamp"))
    qty = float(intent.get("qty") or 0)
    price_hint = intent.get("price_hint")
    return {
        "id": str(run_id),
        "symbol": intent.get("symbol", "UNKNOWN"),
        "side": str(intent.get("side", "buy")).lower(),
        "order_type": str(intent.get("order_type", "market")),
        "time_in_force": intent.get("time_in_force", "day"),
        "qty": qty,
        "filled_qty": 0,
        "limit_price": price_hint,
        "stop_price": None,
        "status": "executed" if intent.get("broker_order_id") else "pending",
        "broker_order_id": intent.get("broker_order_id"),
        "submitted_at": submitted_at,
        "raw_payload": intent,
    }


def intent_to_fill_records(
    order_id: str, intent: Dict[str, object]
) -> List[Dict[str, object]]:
    fills = intent.get("fills") or intent.get("simulated_fills")
    if not isinstance(fills, list):
        return []
    records: List[Dict[str, object]] = []
    for entry in fills:
        if not isinstance(entry, dict):
            continue
        qty = float(entry.get("qty") or entry.get("quantity") or 0)
        price = float(entry.get("price") or entry.get("fill_price") or 0)
        if qty <= 0 or price <= 0:
            continue
        filled_at = _parse_timestamp(entry.get("filled_at")) or datetime.now(
            timezone.utc
        )
        record = {
            "order_id": order_id,
            "symbol": str(entry.get("symbol") or intent.get("symbol", "UNKNOWN")),
            "side": str(entry.get("side") or intent.get("side", "buy")).lower(),
            "qty": qty,
            "price": price,
            "fee": entry.get("fee"),
            "pnl": entry.get("pnl"),
            "filled_at": filled_at,
            "raw_payload": entry,
        }
        records.append(record)
    return records


def persist_order_payload(
    order: Dict[str, object], fills: List[Dict[str, object]] | None = None
) -> None:
    with get_session() as session:
        repo = TradingRepository(session)
        repo.upsert_orders([order])
        if fills:
            repo.record_fills(fills)
        session.commit()


class OrderEventConsumer:
    def __init__(
        self,
        *,
        namespace: str,
        hub: str,
        consumer_group: str,
        storage_account: Optional[str] = None,
        checkpoint_container: Optional[str] = None,
        use_cli_auth: bool = False,
    ) -> None:
        self.namespace = namespace
        self.hub = hub
        self.consumer_group = consumer_group
        self.storage_account = storage_account
        self.checkpoint_container = checkpoint_container
        self.credential = _make_credential(use_cli_auth)
        self._client = None
        self._store = None

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
            logger.warning("[orders] non-json payload: %s", event.body_as_str()[:80])
            return
        order = intent_to_order_record(payload)
        fills = intent_to_fill_records(order["id"], payload)
        persist_order_payload(order, fills)
        enqueued = getattr(event, "enqueued_time", None)
        lag_ms = None
        if isinstance(enqueued, datetime):
            lag_ms = (datetime.now(tz=timezone.utc) - enqueued).total_seconds() * 1000
        logger.info(
            "[orders] persisted symbol=%s qty=%.2f status=%s partition=%s seq=%s lag_ms=%s fills=%s",
            order["symbol"],
            order["qty"],
            order["status"],
            partition_context.partition_id,
            getattr(event, "sequence_number", None),
            None if lag_ms is None else f"{lag_ms:.1f}",
            len(fills),
        )
        if partition_context and self._store:
            partition_context.update_checkpoint(event)

    def run(self) -> None:
        if EventHubConsumerClient is None:
            raise RuntimeError("azure-eventhub is required to run the order consumer")
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

        def _stop_handler(*_: object) -> None:
            nonlocal stop
            stop = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(Exception):
                signal.signal(sig, _stop_handler)

        logger.info(
            "[orders] starting consumer namespace=%s hub=%s group=%s",
            self.namespace,
            self.hub,
            self.consumer_group,
        )
        with client:
            while not stop:
                client.receive(
                    on_event=self._on_event,
                    starting_position="@latest",
                    max_wait_time=5,
                )
        with suppress(Exception):
            self.credential.close()


__all__ = [
    "OrderEventConsumer",
    "intent_to_order_record",
    "intent_to_fill_records",
    "persist_order_payload",
]
