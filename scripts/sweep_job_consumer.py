#!/usr/bin/env python3
from __future__ import annotations

import os

from app.eventbus.sweep_job_consumer import SweepJobEventConsumer


def main() -> None:
    namespace = os.getenv("EH_FQDN", "ai-trader-ehns.servicebus.windows.net")
    hub = os.getenv("EH_HUB_JOBS", "backtest.jobs")
    group = os.getenv("EH_CONSUMER_GROUP_SWEEP", "sweeper")
    job_resource_id = os.getenv("SWEEP_JOB_RESOURCE_ID")
    if not job_resource_id:
        raise SystemExit("SWEEP_JOB_RESOURCE_ID env var is required")
    container_name = os.getenv("SWEEP_JOB_CONTAINER", "sweep-job")
    storage = os.getenv("STORAGE_ACCOUNT") or os.getenv("STG_ACCOUNT")
    checkpoint = os.getenv("CHECKPOINT_CONTAINER")
    use_cli = os.getenv("LOCAL_DEV") == "1"
    consumer = SweepJobEventConsumer(
        namespace=namespace,
        hub=hub,
        consumer_group=group,
        job_resource_id=job_resource_id,
        job_container_name=container_name,
        storage_account=storage,
        checkpoint_container=checkpoint,
        use_cli_auth=use_cli,
    )
    consumer.run()


if __name__ == "__main__":
    main()
