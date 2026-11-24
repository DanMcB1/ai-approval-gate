"""The final side effect must run at most once for a given idempotency key."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from approvalgate.store import execute_once, get_execution, init_db


class IdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "gate.db"
        init_db(self.tmp)

    def test_first_call_executes(self):
        result = execute_once(
            idempotency_key="refund-1",
            workflow_id="wf-1",
            action_type="customer_refund",
            result="SIMULATED refund $2400",
            path=self.tmp,
        )
        self.assertTrue(result["first_time"])
        self.assertEqual(result["attempt_count"], 1)
        stored = get_execution("refund-1", path=self.tmp)
        self.assertEqual(stored["result"], "SIMULATED refund $2400")

    def test_second_call_does_not_replace_result(self):
        execute_once(
            idempotency_key="refund-1",
            workflow_id="wf-1",
            action_type="customer_refund",
            result="SIMULATED refund $2400",
            path=self.tmp,
        )
        second = execute_once(
            idempotency_key="refund-1",
            workflow_id="wf-1",
            action_type="customer_refund",
            result="SHOULD NOT WRITE A SECOND REFUND",
            path=self.tmp,
        )
        self.assertFalse(second["first_time"])
        self.assertEqual(second["attempt_count"], 2)
        self.assertEqual(second["result"], "SIMULATED refund $2400")
        stored = get_execution("refund-1", path=self.tmp)
        self.assertEqual(stored["attempt_count"], 2)
        self.assertEqual(stored["result"], "SIMULATED refund $2400")

    def test_keys_are_independent(self):
        a = execute_once(
            idempotency_key="a",
            workflow_id="wf-a",
            action_type="bulk_email",
            result="email-a",
            path=self.tmp,
        )
        b = execute_once(
            idempotency_key="b",
            workflow_id="wf-b",
            action_type="bulk_email",
            result="email-b",
            path=self.tmp,
        )
        self.assertTrue(a["first_time"])
        self.assertTrue(b["first_time"])


if __name__ == "__main__":
    unittest.main()
