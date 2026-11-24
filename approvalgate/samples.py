"""One-click sample proposals for the demo and for tests."""

from __future__ import annotations

import uuid

from approvalgate.models import Proposal

# Interview / demo defaults: 10 minutes, then 10 more after escalation.
DEFAULT_TIMEOUT = 600
DEFAULT_ESCALATION = 600


def _key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def refund_2400() -> Proposal:
    return Proposal(
        idempotency_key=_key("refund"),
        action_type="customer_refund",
        title="Issue a $2,400 customer refund",
        summary=(
            "Service AI wants to refund $2,400 to a Harbor CDJR customer after a "
            "comeback on a transmission job the shop already charged for."
        ),
        reason="Comeback repair; customer was charged twice and is waiting at the cashier.",
        requested_by="Service assistant (agent)",
        department="Service",
        store="Harbor CDJR",
        amount_usd=2400.0,
        data_classes=["PII", "payment"],
        details={"ro_number": "RO-44118", "customer": "A. Mendoza"},
        timeout_seconds=DEFAULT_TIMEOUT,
        escalation_timeout_seconds=DEFAULT_ESCALATION,
    )


def refund_45() -> Proposal:
    return Proposal(
        idempotency_key=_key("refund"),
        action_type="customer_refund",
        title="Issue a $45 goodwill refund",
        summary="Small courtesy refund for a missed shuttle wait at Lakeside Honda.",
        reason="Customer waited 25 minutes for the service shuttle; manager promised a courtesy credit.",
        requested_by="Service assistant (agent)",
        department="Service",
        store="Lakeside Honda",
        amount_usd=45.0,
        data_classes=["PII"],
        details={"ro_number": "RO-44102"},
        timeout_seconds=DEFAULT_TIMEOUT,
        escalation_timeout_seconds=DEFAULT_ESCALATION,
    )


def change_apr() -> Proposal:
    return Proposal(
        idempotency_key=_key("apr"),
        action_type="change_apr",
        title="Change APR on a funded deal from 6.9% to 4.9%",
        summary=(
            "F&I assistant wants to correct the contract APR on a funded deal at "
            "Westbrook Chevrolet. The deal is already with the lender."
        ),
        reason="Rate was entered as 6.9% but the approved program was 4.9%. Funded last Friday.",
        requested_by="F&I assistant (agent)",
        department="F&I",
        store="Westbrook Chevrolet",
        amount_usd=None,
        data_classes=["PII", "credit", "deal jacket"],
        details={"deal_number": "D-90822", "from_apr": 6.9, "to_apr": 4.9, "lender": "Ally"},
        timeout_seconds=DEFAULT_TIMEOUT,
        escalation_timeout_seconds=DEFAULT_ESCALATION,
    )


def bulk_email_5000() -> Proposal:
    return Proposal(
        idempotency_key=_key("email"),
        action_type="bulk_email",
        title="Bulk-email 5,000 customers a weekend service promo",
        summary="Marketing assistant wants to send a Saturday service-lane promo to 5,000 customers.",
        reason="Open Saturday campaign for all six stores; list is the active-customer file.",
        requested_by="Marketing assistant (agent)",
        department="Marketing",
        store="Group office (central)",
        recipient_count=5000,
        data_classes=["PII"],
        details={"template": "weekend-service-promo-nov", "channel": "email"},
        timeout_seconds=DEFAULT_TIMEOUT,
        escalation_timeout_seconds=DEFAULT_ESCALATION,
    )


def dms_writeback() -> Proposal:
    return Proposal(
        idempotency_key=_key("dms"),
        action_type="dms_writeback",
        title="Write a corrected repair-order note back to the DMS",
        summary=(
            "Service assistant wants to write a revised customer-concern note onto "
            "an open RO in the DMS at Northlake Toyota."
        ),
        reason="The write-up missed a noise concern the customer repeated at check-in.",
        requested_by="Service assistant (agent)",
        department="Service",
        store="Northlake Toyota",
        data_classes=["PII"],
        details={"target": "Repair order concern text", "ro_number": "RO-77831"},
        timeout_seconds=DEFAULT_TIMEOUT,
        escalation_timeout_seconds=DEFAULT_ESCALATION,
    )


def short_timeout_refund() -> Proposal:
    """Same shape as a mid-size refund, but with a 20s + 20s timeout for live demos."""
    proposal = Proposal(
        idempotency_key=_key("refund-short"),
        action_type="customer_refund",
        title="Issue an $800 refund (short timeout demo)",
        summary="Demo proposal with a 20-second approval window, then a 20-second escalation window.",
        reason="Used to show timeout and escalation without waiting ten minutes.",
        requested_by="Service assistant (agent)",
        department="Service",
        store="Parkside Ford",
        amount_usd=800.0,
        data_classes=["PII", "payment"],
        details={"ro_number": "RO-DEMO"},
        timeout_seconds=20,
        escalation_timeout_seconds=20,
    )
    return proposal


def transactional_email() -> Proposal:
    return Proposal(
        idempotency_key=_key("email"),
        action_type="bulk_email",
        title="Send appointment reminders to 8 customers",
        summary="Eight service appointment reminders for tomorrow morning at Summit Kia.",
        reason="Next-day reminders; transactional, not a campaign.",
        requested_by="Service assistant (agent)",
        department="Service",
        store="Summit Kia",
        recipient_count=8,
        data_classes=["PII"],
        details={"template": "appointment-reminder"},
        timeout_seconds=DEFAULT_TIMEOUT,
        escalation_timeout_seconds=DEFAULT_ESCALATION,
    )


SAMPLES = {
    "refund-2400": {
        "title": "Refund $2,400 (needs approval)",
        "factory": refund_2400,
    },
    "refund-45": {
        "title": "Refund $45 (auto-approve)",
        "factory": refund_45,
    },
    "change-apr": {
        "title": "Change funded-deal APR (needs approval)",
        "factory": change_apr,
    },
    "bulk-email": {
        "title": "Email 5,000 customers (needs approval)",
        "factory": bulk_email_5000,
    },
    "dms-writeback": {
        "title": "DMS write-back (needs approval)",
        "factory": dms_writeback,
    },
    "short-timeout": {
        "title": "Short-timeout refund (20s + 20s)",
        "factory": short_timeout_refund,
    },
    "txn-email": {
        "title": "8 appointment reminders (auto-approve)",
        "factory": transactional_email,
    },
}
