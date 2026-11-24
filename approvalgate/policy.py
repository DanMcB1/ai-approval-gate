"""Deterministic approval policy for Lakeside Auto Group.

This is a rules engine, not a model. The same proposal always produces
the same decision, and the rules that fired are returned so the UI and
audit log can show *why* a human was (or was not) required.
"""

from __future__ import annotations

from approvalgate.models import PolicyDecision, Proposal

# Refunds at or above this amount need a person. Below it, a small
# goodwill gesture can auto-approve.
REFUND_AUTO_APPROVE_UNDER = 100.0
# Larger refunds go to the Controller rather than the store desk manager.
REFUND_CONTROLLER_AT = 1000.0
# Transactional emails under this count can auto-approve.
BULK_EMAIL_AUTO_UNDER = 25

POLICY_ID = "lakeside-auto-v1"


def evaluate(proposal: Proposal) -> PolicyDecision:
    """Return auto_approve or require_approval for a proposed action."""
    action = proposal.action_type
    rules: list[str] = []

    if action == "customer_refund":
        return _refund(proposal, rules)
    if action == "change_apr":
        return _apr(proposal, rules)
    if action == "bulk_email":
        return _email(proposal, rules)
    if action == "dms_writeback":
        return _dms(proposal, rules)

    rules.append(f"unknown action type '{action}' — defaulting to require approval")
    return PolicyDecision(
        outcome="require_approval",
        policy_id=POLICY_ID,
        reason="This action type is not in the policy catalog, so a person has to sign off.",
        primary_approver_role="General Manager",
        escalation_role="General Manager",
        rules_fired=rules,
        risk="high",
    )


def _refund(proposal: Proposal, rules: list[str]) -> PolicyDecision:
    amount = float(proposal.amount_usd or 0)
    rules.append(f"refund amount is ${amount:,.2f}")
    if amount < REFUND_AUTO_APPROVE_UNDER:
        rules.append(f"under the ${REFUND_AUTO_APPROVE_UNDER:,.0f} goodwill auto-approve limit")
        return PolicyDecision(
            outcome="auto_approve",
            policy_id=POLICY_ID,
            reason=(
                f"${amount:,.2f} is under the ${REFUND_AUTO_APPROVE_UNDER:,.0f} goodwill limit, "
                "so the policy auto-approves a small customer refund."
            ),
            primary_approver_role=None,
            escalation_role=None,
            rules_fired=rules,
            risk="low",
        )
    if amount >= REFUND_CONTROLLER_AT:
        rules.append(f"at or above the ${REFUND_CONTROLLER_AT:,.0f} Controller threshold")
        primary, risk = "Controller", "high" if amount >= 2000 else "medium"
    else:
        rules.append("desk-manager approval required for mid-size refunds")
        primary, risk = "Desk Manager", "medium"
    return PolicyDecision(
        outcome="require_approval",
        policy_id=POLICY_ID,
        reason=(
            f"A ${amount:,.2f} customer refund is at or above the "
            f"${REFUND_AUTO_APPROVE_UNDER:,.0f} auto-approve limit, so a {primary} must sign off."
        ),
        primary_approver_role=primary,
        escalation_role="General Manager",
        rules_fired=rules,
        risk=risk,
    )


def _apr(proposal: Proposal, rules: list[str]) -> PolicyDecision:
    rules.append("APR changes on a funded deal always require human approval")
    from_apr = proposal.details.get("from_apr")
    to_apr = proposal.details.get("to_apr")
    if from_apr is not None and to_apr is not None:
        rules.append(f"requested change from {from_apr}% to {to_apr}%")
    return PolicyDecision(
        outcome="require_approval",
        policy_id=POLICY_ID,
        reason=(
            "Changing the APR on a funded deal is a compliance-sensitive correction. "
            "An F&I Director has to sign off; it is never auto-approved."
        ),
        primary_approver_role="F&I Director",
        escalation_role="Controller",
        rules_fired=rules,
        risk="high",
    )


def _email(proposal: Proposal, rules: list[str]) -> PolicyDecision:
    count = int(proposal.recipient_count or 0)
    rules.append(f"recipient count is {count:,}")
    sensitive = [d for d in proposal.data_classes if d.lower() in {"credit", "deal jacket", "phi"}]
    if sensitive:
        rules.append("message touches sensitive data classes: " + ", ".join(sensitive))
        return PolicyDecision(
            outcome="require_approval",
            policy_id=POLICY_ID,
            reason="Bulk messages that mention credit or deal information need a Marketing Manager to sign off.",
            primary_approver_role="Marketing Manager",
            escalation_role="General Manager",
            rules_fired=rules,
            risk="high",
        )
    if count < BULK_EMAIL_AUTO_UNDER:
        rules.append(f"under the {BULK_EMAIL_AUTO_UNDER} recipient transactional auto-approve limit")
        return PolicyDecision(
            outcome="auto_approve",
            policy_id=POLICY_ID,
            reason=(
                f"{count} recipients is under the {BULK_EMAIL_AUTO_UNDER} transactional limit, "
                "so a small operational email can auto-approve."
            ),
            primary_approver_role=None,
            escalation_role=None,
            rules_fired=rules,
            risk="low",
        )
    risk = "high" if count >= 1000 else "medium"
    rules.append("bulk outreach requires Marketing Manager approval")
    return PolicyDecision(
        outcome="require_approval",
        policy_id=POLICY_ID,
        reason=(
            f"Emailing {count:,} customers is over the {BULK_EMAIL_AUTO_UNDER} transactional limit, "
            "so a Marketing Manager must sign off before anything is sent."
        ),
        primary_approver_role="Marketing Manager",
        escalation_role="General Manager",
        rules_fired=rules,
        risk=risk,
    )


def _dms(proposal: Proposal, rules: list[str]) -> PolicyDecision:
    rules.append("write-back to the system of record always requires human approval")
    target = proposal.details.get("target") or "DMS record"
    rules.append(f"write target: {target}")
    return PolicyDecision(
        outcome="require_approval",
        policy_id=POLICY_ID,
        reason=(
            f"Writing back to the DMS ({target}) can change a system of record. "
            "An IT Owner must sign off; the agent is not allowed to write on its own."
        ),
        primary_approver_role="IT Owner",
        escalation_role="General Manager",
        rules_fired=rules,
        risk="high",
    )


def next_phase_on_timeout(current_phase: str) -> str:
    """Pure timeout/escalation state machine.

    waiting_primary --timeout--> escalated
    escalated      --timeout--> timed_out (auto-reject)
    """
    if current_phase == "waiting_primary":
        return "escalated"
    if current_phase == "escalated":
        return "timed_out"
    raise ValueError(f"timeout is not valid in phase {current_phase!r}")
