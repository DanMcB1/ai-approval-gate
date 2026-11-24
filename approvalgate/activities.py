"""Temporal activities: audit, mock inbox, and the idempotent side effect.

Activities may do I/O. The workflow itself stays deterministic.
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from approvalgate import store
from approvalgate.slack_adapter import maybe_notify_slack


@activity.defn
def record_audit(event: dict[str, Any]) -> int:
    return store.record_event(
        workflow_id=event["workflow_id"],
        idempotency_key=event["idempotency_key"],
        event_type=event["event_type"],
        actor=event.get("actor", "system"),
        actor_role=event.get("actor_role", "system"),
        message=event["message"],
        payload=event.get("payload"),
    )


@activity.defn
def publish_inbox(row: dict[str, Any]) -> None:
    store.upsert_inbox(row)
    # Optional real Slack is off by default and no-ops unless explicitly enabled.
    maybe_notify_slack(row)


@activity.defn
def execute_side_effect(payload: dict[str, Any]) -> dict[str, Any]:
    """Simulate performing the high-stakes action, at most once."""
    action = payload["action_type"]
    key = payload["idempotency_key"]
    if action == "customer_refund":
        result = f"SIMULATED refund of ${payload.get('amount_usd') or 0:,.2f} (not sent to any payment system)"
    elif action == "change_apr":
        details = payload.get("details") or {}
        result = (
            f"SIMULATED APR change {details.get('from_apr')}% → {details.get('to_apr')}% "
            f"on deal {details.get('deal_number')} (not written to any lender or DMS)"
        )
    elif action == "bulk_email":
        result = (
            f"SIMULATED email to {int(payload.get('recipient_count') or 0):,} customers "
            "(not delivered to anyone)"
        )
    elif action == "dms_writeback":
        details = payload.get("details") or {}
        result = f"SIMULATED DMS write-back to {details.get('target', 'DMS')} (not connected to a real DMS)"
    else:
        result = f"SIMULATED action {action}"

    outcome = store.execute_once(
        idempotency_key=key,
        workflow_id=payload["workflow_id"],
        action_type=action,
        result=result,
    )
    activity.logger.info(
        "execute_side_effect key=%s first_time=%s attempts=%s",
        key,
        outcome["first_time"],
        outcome["attempt_count"],
    )
    return outcome
