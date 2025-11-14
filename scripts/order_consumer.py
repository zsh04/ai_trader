#!/usr/bin/env python3
"""Event Hubs consumer for exec.orders."""

from __future__ import annotations

import os

from app.eventbus.order_consumer import OrderEventConsumer


def main() -> None:
    namespace = os.getenv("EH_FQDN", "ai-trader-ehns.servicebus.windows.net")
    hub = os.getenv("EH_HUB_ORDERS", "exec.orders")
    group = os.getenv("EH_CONSUMER_GROUP", "orchestrator")
    storage = os.getenv("STORAGE_ACCOUNT")
    container = os.getenv("CHECKPOINT_CONTAINER")
    use_cli = os.getenv("LOCAL_DEV") == "1"

    consumer = OrderEventConsumer(
        namespace=namespace,
        hub=hub,
        consumer_group=group,
        storage_account=storage,
        checkpoint_container=container,
        use_cli_auth=use_cli,
    )
    consumer.run()


if __name__ == "__main__":
    main()
