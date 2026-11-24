"""CLI: start a sample, list inbox, or run the crash test.

  python -m approvalgate worker
  python -m approvalgate crash-test
  python -m approvalgate start refund-2400
"""

from __future__ import annotations

import argparse
import json
import sys

from approvalgate.samples import SAMPLES
from approvalgate.store import counts, list_audit, list_inbox


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Approval gate utilities (portfolio demo).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("worker", help="Run the Temporal worker")
    sub.add_parser("crash-test", help="Kill the worker mid-wait and prove a single execution")
    start = sub.add_parser("start", help="Start a sample workflow")
    start.add_argument("sample", choices=sorted(SAMPLES))
    sub.add_parser("status", help="Print inbox counts and recent audit events")

    args = parser.parse_args(argv)
    if args.cmd == "worker":
        from approvalgate.worker import main as worker_main

        return worker_main()
    if args.cmd == "crash-test":
        from approvalgate.crash_test import main as crash_main

        return crash_main()
    if args.cmd == "start":
        from approvalgate.client import start_proposal

        proposal = SAMPLES[args.sample]["factory"]()
        info = start_proposal(proposal)
        print(json.dumps({"proposal": proposal.to_dict(), "start": info}, indent=2, default=str))
        return 0
    if args.cmd == "status":
        print(json.dumps({"counts": counts(), "inbox": list_inbox(), "audit": list_audit(20)}, indent=2, default=str))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
