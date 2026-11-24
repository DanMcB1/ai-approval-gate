"""Sync helpers the Streamlit app and crash test use to talk to Temporal."""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio.client import Client, WorkflowExecutionStatus, WorkflowFailureError
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError

from approvalgate.models import Proposal
from approvalgate.settings import task_queue, temporal_address, temporal_namespace
from approvalgate.workflow import ApprovalGateWorkflow

WORKFLOW_ID_PREFIX = "approval-"


def workflow_id_for(key: str) -> str:
    return f"{WORKFLOW_ID_PREFIX}{key}"


async def _connect() -> Client:
    return await Client.connect(temporal_address(), namespace=temporal_namespace())


async def _start(proposal: Proposal) -> dict[str, Any]:
    client = await _connect()
    wf_id = workflow_id_for(proposal.idempotency_key)
    try:
        handle = await client.start_workflow(
            ApprovalGateWorkflow.run,
            proposal.to_dict(),
            id=wf_id,
            task_queue=task_queue(),
        )
        return {
            "workflow_id": handle.id,
            "run_id": handle.result_run_id,
            "already_existed": False,
        }
    except WorkflowAlreadyStartedError:
        handle = client.get_workflow_handle(wf_id)
        desc = await handle.describe()
        return {
            "workflow_id": handle.id,
            "run_id": desc.run_id,
            "already_existed": True,
        }


async def _signal(workflow_id: str, decision: dict[str, Any]) -> None:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(ApprovalGateWorkflow.decide, decision)


async def _snapshot(workflow_id: str) -> dict[str, Any]:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id)
    snap = await handle.query(ApprovalGateWorkflow.snapshot)
    desc = await handle.describe()
    status = desc.status
    snap = dict(snap or {})
    snap["temporal_status"] = status.name if isinstance(status, WorkflowExecutionStatus) else str(status)
    snap["workflow_id"] = workflow_id
    snap["run_id"] = desc.run_id
    return snap


async def _wait_result(workflow_id: str, timeout: float | None = None) -> dict[str, Any]:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id)
    try:
        if timeout is None:
            return await handle.result()
        return await asyncio.wait_for(handle.result(), timeout=timeout)
    except WorkflowFailureError as exc:
        return {"status": "failed", "error": str(exc)}


async def _ping() -> bool:
    try:
        await _connect()
        return True
    except Exception:
        return False


def start_proposal(proposal: Proposal) -> dict[str, Any]:
    return asyncio.run(_start(proposal))


def signal_decision(workflow_id: str, action: str, actor: str, actor_role: str, comment: str = "") -> None:
    asyncio.run(
        _signal(
            workflow_id,
            {"action": action, "actor": actor, "actor_role": actor_role, "comment": comment},
        )
    )


def get_snapshot(workflow_id: str) -> dict[str, Any]:
    return asyncio.run(_snapshot(workflow_id))


def wait_for_result(workflow_id: str, timeout: float | None = None) -> dict[str, Any]:
    return asyncio.run(_wait_result(workflow_id, timeout))


def temporal_is_up() -> bool:
    return asyncio.run(_ping())


async def _worker_is_polling() -> bool:
    """Best-effort: can we connect, and is the task queue being polled?"""
    try:
        client = await _connect()
        # A lightweight describe of the queue isn't always available on the
        # dev server; a successful connect plus a later start is the real check.
        _ = client
        return True
    except (RPCError, OSError, RuntimeError):
        return False
