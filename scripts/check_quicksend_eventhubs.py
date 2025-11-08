# scripts/quickrecv.py
import os, asyncio
from azure.identity.aio import AzureCliCredential
from azure.eventhub.aio import EventHubConsumerClient

EH_FQDN=os.environ["EH_FQDN"]              # ai-trader-ehns.servicebus.windows.net
HUB=os.environ["EH_HUB_BARS"]              # bars.raw
CG=os.environ.get("EH_CONSUMER_GROUP","orchestrator")

async def on_event(partition_context, event):
    print(partition_context.partition_id, event.body_as_str())
    await partition_context.update_checkpoint(event)  # noop without blob store

async def main():
    cred = AzureCliCredential()
    client = EventHubConsumerClient(
        fully_qualified_namespace=EH_FQDN,
        eventhub_name=HUB,
        consumer_group=CG,
        credential=cred,
    )
    async with cred, client:
        await client.receive(on_event=on_event, starting_position="-1")  # from beginning

if __name__ == "__main__":
    asyncio.run(main())