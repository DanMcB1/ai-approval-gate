"""Timeout / escalation state machine."""

from __future__ import annotations

import unittest

from approvalgate.policy import next_phase_on_timeout


class TimeoutMachineTests(unittest.TestCase):
    def test_primary_timeout_escalates(self):
        self.assertEqual(next_phase_on_timeout("waiting_primary"), "escalated")

    def test_escalation_timeout_auto_rejects(self):
        self.assertEqual(next_phase_on_timeout("escalated"), "timed_out")

    def test_invalid_phase_raises(self):
        with self.assertRaises(ValueError):
            next_phase_on_timeout("approved")


class SlackAdapterDefaultTests(unittest.TestCase):
    def test_real_slack_is_off_by_default(self):
        from approvalgate.slack_adapter import maybe_notify_slack, slack_is_enabled

        self.assertFalse(slack_is_enabled())
        # Must not raise and must not attempt a network call.
        maybe_notify_slack({"title": "should no-op", "workflow_id": "x"})


if __name__ == "__main__":
    unittest.main()
