"""Temporal worker process. Kill this mid-wait; restart it; the workflow resumes."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from approvalgate.activities import execute_side_effect, publish_inbox, record_audit
from approvalgate.settings import task_queue, temporal_address, temporal_namespace
from approvalgate.store import init_db
from approvalgate.workflow import ApprovalGateWorkflow

log = logging.getLogger("approvalgate.worker")


async def run_worker() -> None:
    init_db()
    log.info("Connecting to Temporal at %s (namespace %s)", temporal_address(), temporal_namespace())
    client = await Client.connect(temporal_address(), namespace=temporal_namespace())
    with ThreadPoolExecutor(max_workers=8) as pool:
        worker = Worker(
            client,
            task_queue=task_queue(),
            workflows=[ApprovalGateWorkflow],
            activities=[record_audit, publish_inbox, execute_side_effect],
            activity_executor=pool,
        )
        log.info("Worker started on task queue %s", task_queue())
        await worker.run()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        log.info("Worker stopped")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
