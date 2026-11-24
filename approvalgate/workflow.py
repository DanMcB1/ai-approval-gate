"""Temporal workflow: pause a high-stakes action until a person decides.

The workflow code is deterministic. All I/O happens in activities.
Timeouts use Temporal timers so they survive a worker crash.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from approvalgate.policy import evaluate, next_phase_on_timeout
from approvalgate.models import PolicyDecision, Proposal

with workflow.unsafe.imports_passed_through():
    from approvalgate.activities import execute_side_effect, publish_inbox, record_audit


RETRY = RetryPolicy(maximum_attempts=5, initial_interval=timedelta(milliseconds=200))
SHORT = timedelta(seconds=15)


def _proposal(data: dict[str, Any]) -> Proposal:
    return Proposal.from_dict(data)


@workflow.defn
class ApprovalGateWorkflow:
    def __init__(self) -> None:
        self._decision: dict[str, Any] | None = None
        self._phase: str = "started"
        self._status: str = "started"
        self._policy: dict[str, Any] | None = None
        self._execution: dict[str, Any] | None = None
        self._proposal: dict[str, Any] | None = None

    @workflow.signal
    def decide(self, decision: dict[str, Any]) -> None:
        """First decisive signal wins. Later clicks are ignored by the workflow."""
        if self._decision is None and decision.get("action") in {"approve", "reject"}:
            self._decision = {
                "action": decision["action"],
                "actor": decision.get("actor") or "unknown",
                "actor_role": decision.get("actor_role") or "",
                "comment": decision.get("comment") or "",
            }

    @workflow.query
    def snapshot(self) -> dict[str, Any]:
        return {
            "phase": self._phase,
            "status": self._status,
            "policy": self._policy,
            "decision": self._decision,
            "execution": self._execution,
            "proposal": self._proposal,
        }

    @workflow.run
    async def run(self, proposal_data: dict[str, Any]) -> dict[str, Any]:
        proposal = _proposal(proposal_data)
        self._proposal = proposal.to_dict()
        workflow_id = workflow.info().workflow_id
        policy = evaluate(proposal)
        self._policy = policy.to_dict()

        await self._audit(
            workflow_id,
            proposal,
            "proposed",
            proposal.requested_by,
            "agent",
            f"Agent proposed: {proposal.title}",
            {"proposal": proposal.to_dict()},
        )
        await self._audit(
            workflow_id,
            proposal,
            "policy_evaluated",
            "policy engine",
            "system",
            policy.reason,
            policy.to_dict(),
        )

        if policy.outcome == "auto_approve":
            self._phase = "auto_approved"
            self._status = "auto_approved"
            self._execution = await self._execute(workflow_id, proposal)
            await self._publish(workflow_id, proposal, policy)
            await self._audit(
                workflow_id,
                proposal,
                "executed",
                "policy engine",
                "system",
                "Auto-approved and executed once."
                + ("" if self._execution.get("first_time") else " (idempotent replay — already executed)"),
                self._execution,
            )
            return self.snapshot()

        # Human path
        self._phase = "waiting_primary"
        self._status = "waiting_primary"
        await self._publish(workflow_id, proposal, policy)
        await self._audit(
            workflow_id,
            proposal,
            "waiting_for_approval",
            "approval gate",
            "system",
            f"Waiting for a {policy.primary_approver_role} to approve or reject "
            f"({proposal.timeout_seconds}s until escalation).",
            {"timeout_seconds": proposal.timeout_seconds},
        )

        decided = await self._wait_for_decision(proposal.timeout_seconds)
        if not decided:
            self._phase = next_phase_on_timeout("waiting_primary")
            self._status = "escalated"
            await self._publish(workflow_id, proposal, policy)
            await self._audit(
                workflow_id,
                proposal,
                "escalated",
                "approval gate",
                "system",
                f"No response from {policy.primary_approver_role}. "
                f"Escalated to {policy.escalation_role} "
                f"({proposal.escalation_timeout_seconds}s until auto-reject).",
                {
                    "from_role": policy.primary_approver_role,
                    "to_role": policy.escalation_role,
                },
            )
            decided = await self._wait_for_decision(proposal.escalation_timeout_seconds)

        if not decided:
            self._phase = next_phase_on_timeout("escalated")
            self._status = "timed_out"
            await self._publish(workflow_id, proposal, policy)
            await self._audit(
                workflow_id,
                proposal,
                "timed_out",
                "approval gate",
                "system",
                "No response after escalation. The action was auto-rejected and will not run.",
                {},
            )
            return self.snapshot()

        decision = self._decision or {}
        if decision.get("action") == "approve":
            self._phase = "approved"
            self._status = "approved"
            await self._audit(
                workflow_id,
                proposal,
                "approved",
                decision.get("actor", "approver"),
                decision.get("actor_role", ""),
                decision.get("comment") or "Approved.",
                decision,
            )
            self._execution = await self._execute(workflow_id, proposal)
            await self._publish(workflow_id, proposal, policy)
            await self._audit(
                workflow_id,
                proposal,
                "executed",
                decision.get("actor", "approver"),
                decision.get("actor_role", ""),
                "Approved action executed once."
                + ("" if self._execution.get("first_time") else " (idempotent replay — already executed)"),
                self._execution,
            )
        else:
            self._phase = "rejected"
            self._status = "rejected"
            await self._publish(workflow_id, proposal, policy)
            await self._audit(
                workflow_id,
                proposal,
                "rejected",
                decision.get("actor", "approver"),
                decision.get("actor_role", ""),
                decision.get("comment") or "Rejected.",
                decision,
            )
        return self.snapshot()

    async def _wait_for_decision(self, seconds: int) -> bool:
        if self._decision is not None:
            return True
        try:
            await workflow.wait_condition(
                lambda: self._decision is not None,
                timeout=timedelta(seconds=max(1, int(seconds))),
            )
            return self._decision is not None
        except TimeoutError:
            return self._decision is not None

    async def _audit(
        self,
        workflow_id: str,
        proposal: Proposal,
        event_type: str,
        actor: str,
        actor_role: str,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        await workflow.execute_activity(
            record_audit,
            {
                "workflow_id": workflow_id,
                "idempotency_key": proposal.idempotency_key,
                "event_type": event_type,
                "actor": actor,
                "actor_role": actor_role,
                "message": message,
                "payload": payload,
            },
            start_to_close_timeout=SHORT,
            retry_policy=RETRY,
        )

    async def _publish(
        self,
        workflow_id: str,
        proposal: Proposal,
        policy: PolicyDecision,
    ) -> None:
        await workflow.execute_activity(
            publish_inbox,
            {
                "workflow_id": workflow_id,
                "idempotency_key": proposal.idempotency_key,
                "action_type": proposal.action_type,
                "title": proposal.title,
                "summary": proposal.summary,
                "reason": proposal.reason,
                "department": proposal.department,
                "store": proposal.store,
                "requested_by": proposal.requested_by,
                "amount_usd": proposal.amount_usd,
                "recipient_count": proposal.recipient_count,
                "primary_role": policy.primary_approver_role,
                "escalation_role": policy.escalation_role,
                "policy_reason": policy.reason,
                "risk": policy.risk,
                "phase": self._phase,
                "status": self._status,
                "payload": {"policy": policy.to_dict(), "details": proposal.details},
            },
            start_to_close_timeout=SHORT,
            retry_policy=RETRY,
        )

    async def _execute(self, workflow_id: str, proposal: Proposal) -> dict[str, Any]:
        return await workflow.execute_activity(
            execute_side_effect,
            {
                "workflow_id": workflow_id,
                "idempotency_key": proposal.idempotency_key,
                "action_type": proposal.action_type,
                "amount_usd": proposal.amount_usd,
                "recipient_count": proposal.recipient_count,
                "details": proposal.details,
            },
            start_to_close_timeout=SHORT,
            retry_policy=RETRY,
        )
