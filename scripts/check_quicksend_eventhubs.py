#!/usr/bin/env python3
import asyncio
import datetime as dt
import json
import os

from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient
from azure.identity.aio import DefaultAzureCredential

FQDN = os.environ.get("EH_FQDN")  # e.g. ai-trader-ehns.servicebus.windows.net
HUB  = os.environ.get("EH_HUB", "bars.raw")
N    = int(os.environ.get("N", "5"))
PK   = os.environ.get("PARTITION_KEY", "demo")

def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

async def main():
    if not FQDN:
        raise SystemExit("Set EH_FQDN env var (e.g. ai-trader-ehns.servicebus.windows.net)")

    cred = DefaultAzureCredential()
    client = EventHubProducerClient(
        fully_qualified_namespace=FQDN,
        eventhub_name=HUB,
        credential=cred,
        logging_enable=True,
    )

    async with client, cred:
        batch = await client.create_batch(partition_key=PK)
        for i in range(N):
            payload = {
                "type": "quicksend",
                "i": i,
                "ts": _now(),
                "symbol": os.environ.get("SYMBOL", "AAPL"),
                "source": "scripts/check_quicksend_eventhubs.py",
            }
            try:
                batch.add(EventData(json.dumps(payload)))
            except ValueError:
                await client.send_batch(batch)
                batch = await client.create_batch(partition_key=PK)
                batch.add(EventData(json.dumps(payload)))
        await client.send_batch(batch)
        print(f"Sent {N} event(s) to {HUB} (partition_key={PK}) via {FQDN}")

if __name__ == "__main__":
    asyncio.run(main())
