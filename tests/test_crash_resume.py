"""End-to-end: worker is killed mid-wait, restarted, and the action runs once.

Requires the Temporal CLI at bin/temporal (run.sh downloads it).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from approvalgate.settings import ROOT


class CrashResumeTests(unittest.TestCase):
    def test_resume_after_worker_kill_executes_once(self):
        binary = ROOT / "bin" / "temporal"
        if not binary.exists():
            self.skipTest("Temporal CLI is not at bin/temporal; run ./run.sh first")
        from approvalgate.crash_test import main

        self.assertEqual(main(), 0)


if __name__ == "__main__":
    unittest.main()
