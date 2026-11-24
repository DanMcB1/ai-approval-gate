"""Policy engine: auto-approve vs require a human, and who signs off."""

from __future__ import annotations

import unittest

from approvalgate.models import Proposal
from approvalgate.policy import (
    BULK_EMAIL_AUTO_UNDER,
    REFUND_AUTO_APPROVE_UNDER,
    REFUND_CONTROLLER_AT,
    evaluate,
)
from approvalgate.samples import (
    bulk_email_5000,
    change_apr,
    dms_writeback,
    refund_45,
    refund_2400,
    transactional_email,
)


def _proposal(**kwargs) -> Proposal:
    base = dict(
        idempotency_key="test-key",
        action_type="customer_refund",
        title="t",
        summary="s",
        reason="r",
        requested_by="agent",
        department="Service",
        store="Lakeside Honda",
    )
    base.update(kwargs)
    return Proposal(**base)


class RefundPolicyTests(unittest.TestCase):
    def test_small_goodwill_auto_approves(self):
        decision = evaluate(refund_45())
        self.assertEqual(decision.outcome, "auto_approve")
        self.assertIsNone(decision.primary_approver_role)
        self.assertEqual(decision.risk, "low")
        self.assertTrue(any("goodwill" in r or "under" in r for r in decision.rules_fired))

    def test_2400_refund_needs_controller(self):
        decision = evaluate(refund_2400())
        self.assertEqual(decision.outcome, "require_approval")
        self.assertEqual(decision.primary_approver_role, "Controller")
        self.assertEqual(decision.escalation_role, "General Manager")
        self.assertEqual(decision.risk, "high")
        self.assertGreaterEqual(refund_2400().amount_usd, REFUND_CONTROLLER_AT)

    def test_mid_size_refund_needs_desk_manager(self):
        decision = evaluate(_proposal(action_type="customer_refund", amount_usd=250))
        self.assertEqual(decision.outcome, "require_approval")
        self.assertEqual(decision.primary_approver_role, "Desk Manager")
        self.assertGreaterEqual(250, REFUND_AUTO_APPROVE_UNDER)


class OtherPolicyTests(unittest.TestCase):
    def test_apr_change_always_requires_fi_director(self):
        decision = evaluate(change_apr())
        self.assertEqual(decision.outcome, "require_approval")
        self.assertEqual(decision.primary_approver_role, "F&I Director")
        self.assertEqual(decision.escalation_role, "Controller")

    def test_bulk_email_5000_needs_marketing(self):
        decision = evaluate(bulk_email_5000())
        self.assertEqual(decision.outcome, "require_approval")
        self.assertEqual(decision.primary_approver_role, "Marketing Manager")
        self.assertEqual(decision.risk, "high")

    def test_small_transactional_email_auto_approves(self):
        proposal = transactional_email()
        self.assertLess(proposal.recipient_count, BULK_EMAIL_AUTO_UNDER)
        decision = evaluate(proposal)
        self.assertEqual(decision.outcome, "auto_approve")

    def test_email_with_credit_content_requires_approval_even_if_small(self):
        decision = evaluate(
            _proposal(
                action_type="bulk_email",
                recipient_count=5,
                data_classes=["credit"],
            )
        )
        self.assertEqual(decision.outcome, "require_approval")

    def test_dms_writeback_always_requires_it(self):
        decision = evaluate(dms_writeback())
        self.assertEqual(decision.outcome, "require_approval")
        self.assertEqual(decision.primary_approver_role, "IT Owner")

    def test_unknown_action_requires_approval(self):
        decision = evaluate(_proposal(action_type="wire_transfer"))
        self.assertEqual(decision.outcome, "require_approval")

    def test_policy_is_deterministic(self):
        a = evaluate(refund_2400())
        b = evaluate(refund_2400())
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
