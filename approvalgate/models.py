"""Shared data shapes. These are plain dict-friendly dataclasses for Temporal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ACTION_TYPES = (
    "customer_refund",
    "change_apr",
    "bulk_email",
    "dms_writeback",
)

ACTION_LABELS = {
    "customer_refund": "Customer refund",
    "change_apr": "Change APR on a funded deal",
    "bulk_email": "Bulk customer email",
    "dms_writeback": "Write back to the DMS",
}

# Demo personas an interviewer can "act as" in the mock inbox.
PERSONAS = [
    {"name": "Dana Ruiz", "role": "Desk Manager"},
    {"name": "Pat Kim", "role": "Controller"},
    {"name": "Morgan Blake", "role": "F&I Director"},
    {"name": "Avery Chen", "role": "Marketing Manager"},
    {"name": "Chris Park", "role": "IT Owner"},
    {"name": "Jordan Hale", "role": "General Manager"},
]


@dataclass
class Proposal:
    idempotency_key: str
    action_type: str
    title: str
    summary: str
    reason: str
    requested_by: str
    department: str
    store: str
    amount_usd: float | None = None
    recipient_count: int | None = None
    data_classes: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 600
    escalation_timeout_seconds: int = 600

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Proposal":
        allowed = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**allowed)


@dataclass
class PolicyDecision:
    outcome: str  # auto_approve | require_approval
    policy_id: str
    reason: str
    primary_approver_role: str | None
    escalation_role: str | None
    rules_fired: list[str]
    risk: str  # low | medium | high

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyDecision":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class Decision:
    action: str  # approve | reject
    actor: str
    actor_role: str
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
