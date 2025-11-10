#!/usr/bin/env python3
import asyncio
import contextlib
import datetime as dt
import logging
import os
import signal

from azure.eventhub.aio import EventHubConsumerClient
from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

FQDN = os.getenv("EH_FQDN", "ai-trader-ehns.servicebus.windows.net")
HUB = os.getenv("EH_HUB", "bars.raw")
GROUP = os.getenv("EH_CONSUMER_GROUP", "orchestrator")
STG = os.getenv("STORAGE_ACCOUNT", "aitraderblobstore")
CONT = os.getenv("CHECKPOINT_CONTAINER", "eh-checkpoints")
START = os.getenv("EH_START", "@latest")  # "@latest" or "-1"
TIMEOUT_S = int(os.getenv("RECV_TIMEOUT_S", "120"))  # <-- longer
LOCAL = os.getenv("LOCAL_DEV") == "1"
NOCKPT = os.getenv("DISABLE_CHECKPOINT") == "1"  # set to 1 to skip blob checkpoints

logging.basicConfig(level=logging.INFO)
# Quieter by default; flip AZURE_DEBUG=1 to see wire logs
if os.getenv("AZURE_DEBUG") == "1":
    logging.getLogger("azure.eventhub").setLevel(logging.INFO)
    logging.getLogger("azure.identity").setLevel(logging.INFO)
else:
    logging.getLogger("azure.eventhub").setLevel(logging.WARNING)
    logging.getLogger("azure.identity").setLevel(logging.WARNING)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


stop_event = asyncio.Event()


def _handle_stop(*_: object) -> None:
    stop_event.set()


def make_cred():
    return AzureCliCredential() if LOCAL else DefaultAzureCredential()


async def preflight(blob: BlobServiceClient):
    if NOCKPT:
        return
    cn = blob.get_container_client(CONT)
    try:
        await cn.create_container()
    except Exception as exc:
        logging.debug("container creation skipped: %s", exc)
    probe = cn.get_blob_client("sanity/_receiver_probe.txt")
    await probe.upload_blob(f"probe {now()}".encode(), overwrite=True)
    async for _ in cn.walk_blobs(name_starts_with="sanity/"):
        break


async def main():
    print(f"AUTH_MODE={'AzureCliCredential' if LOCAL else 'DefaultAzureCredential'}")
    print(
        f"CHECKPOINTS={'DISABLED' if NOCKPT else 'ENABLED'}  start={START}  group={GROUP}"
    )
    if not NOCKPT:
        print(f"BLOB_URL=https://{STG}.blob.core.windows.net/{CONT}")

    cred = make_cred()
    blob = (
        BlobServiceClient(
            account_url=f"https://{STG}.blob.core.windows.net",
            credential=cred,
        )
        if not NOCKPT
        else None
    )
    if blob:
        await preflight(blob)

    store = (
        None
        if NOCKPT
        else BlobCheckpointStore(
            blob_account_url=f"https://{STG}.blob.core.windows.net",
            container_name=CONT,
            credential=cred,
        )
    )
    client = EventHubConsumerClient(
        fully_qualified_namespace=FQDN,
        eventhub_name=HUB,
        consumer_group=GROUP,
        checkpoint_store=store,
        credential=cred,
        logging_enable=(os.getenv("AZURE_DEBUG") == "1"),
    )

    async def on_event(pc, ev):
        # Prefer SDK-populated attributes over AMQP system_properties
        seq = getattr(ev, "sequence_number", None)
        enq = getattr(ev, "enqueued_time", None)
        off = getattr(ev, "offset", None)
        key = getattr(ev, "partition_key", None)
        print(
            f"[{pc.partition_id}] seq={seq} enq={enq} off={off} pkey={key} body={ev.body_as_str()[:120]}"
        )
        if store:  # only checkpoint when enabled
            await pc.update_checkpoint(ev)

    try:
        async with client, cred:
            # optional: print partitions for visibility
            pids = await client.get_partition_ids()
            print("Partitions:", ",".join(pids))
            task = asyncio.create_task(
                client.receive(on_event=on_event, starting_position=START)
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=TIMEOUT_S)
            except asyncio.TimeoutError:
                pass
            finally:
                task.cancel()
                # Swallow asyncio.CancelledError on 3.13+ (it may not inherit Exception)
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
    finally:
        if blob:
            with contextlib.suppress(Exception):
                await blob.close()
        with contextlib.suppress(Exception):
            await cred.close()


if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(Exception):
            signal.signal(sig, _handle_stop)
    asyncio.run(main())
