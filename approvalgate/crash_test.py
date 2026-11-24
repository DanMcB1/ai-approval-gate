"""Scripted crash test: kill the worker mid-wait, restart, approve once.

Proves the headline property of the demo:

1. A refund that needs approval sits in a durable wait.
2. If the worker process is killed, Temporal still has the workflow.
3. After the worker comes back, the same pending approval is still there.
4. One Approve click runs the side effect exactly once (idempotency key).
5. A second Approve or a replayed execute does not issue a second refund.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from approvalgate.settings import ROOT


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_port(host: str, port: int, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last = exc
            time.sleep(0.15)
    raise RuntimeError(f"Timed out waiting for {host}:{port} ({last})")


def _temporal_bin() -> Path:
    path = ROOT / "bin" / "temporal"
    if not path.exists():
        raise RuntimeError(
            "Temporal CLI not found at bin/temporal. Run ./run.sh once, or see the README."
        )
    return path


class Stack:
    """An isolated Temporal server + worker for the crash test."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.server: subprocess.Popen | None = None
        self.worker: subprocess.Popen | None = None
        self._log_handles: list = []
        self.port = _free_port()
        self.ui_port = _free_port()
        self.http_port = _free_port()
        self.metrics_port = _free_port()
        self.env = os.environ.copy()
        self.env.update(
            {
                "TEMPORAL_PORT": str(self.port),
                "TEMPORAL_UI_PORT": str(self.ui_port),
                "TEMPORAL_HTTP_PORT": str(self.http_port),
                "TEMPORAL_METRICS_PORT": str(self.metrics_port),
                "TEMPORAL_ADDRESS": f"127.0.0.1:{self.port}",
                "TEMPORAL_NAMESPACE": "default",
                "APPROVAL_GATE_TASK_QUEUE": "approval-gate-crash",
                "APPROVAL_GATE_DATA": str(base),
                "APPROVAL_GATE_DB": str(base / "approval_gate.db"),
                "TEMPORAL_DB": str(base / "temporal.db"),
                "PYTHONUNBUFFERED": "1",
            }
        )

    def start_server(self) -> None:
        cmd = [
            str(_temporal_bin()),
            "server",
            "start-dev",
            "--headless",
            "--ip",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--http-port",
            str(self.http_port),
            "--metrics-port",
            str(self.metrics_port),
            "--db-filename",
            str(self.base / "temporal.db"),
        ]
        log_path = self.base / "temporal.log"
        handle = log_path.open("w")
        self._log_handles.append(handle)
        self.server = subprocess.Popen(
            cmd,
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=self.env,
        )
        _wait_port("127.0.0.1", self.port, timeout=30)

    def start_worker(self) -> None:
        log_path = self.base / "worker.log"
        handle = log_path.open("w")
        self._log_handles.append(handle)
        self.worker = subprocess.Popen(
            [sys.executable, "-m", "approvalgate", "worker"],
            cwd=str(ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=self.env,
        )
        # Give the worker a moment to poll the task queue.
        time.sleep(1.2)
        if self.worker.poll() is not None:
            raise RuntimeError(f"Worker exited early: {log_path.read_text()[-2000:]}")

    def kill_worker(self) -> None:
        if self.worker and self.worker.poll() is None:
            self.worker.send_signal(signal.SIGKILL)
            try:
                self.worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def stop(self) -> None:
        self.kill_worker()
        if self.server and self.server.poll() is None:
            self.server.send_signal(signal.SIGTERM)
            try:
                self.server.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.server.send_signal(signal.SIGKILL)
                self.server.wait(timeout=3)
        for handle in self._log_handles:
            try:
                handle.close()
            except Exception:
                pass
        self._log_handles = []


def _prepare_imports(env: dict[str, str]) -> None:
    """Apply env before we import client/store settings."""
    os.environ.update(env)


def run_crash_test() -> dict:
    from approvalgate.client import get_snapshot, signal_decision, start_proposal, wait_for_result
    from approvalgate.samples import refund_2400
    from approvalgate.store import get_execution, list_inbox

    proposal = refund_2400()
    key = proposal.idempotency_key
    start = start_proposal(proposal)
    wf_id = start["workflow_id"]

    deadline = time.time() + 20
    phase = None
    while time.time() < deadline:
        try:
            snap = get_snapshot(wf_id)
            phase = snap.get("phase") or snap.get("status")
            if phase == "waiting_primary":
                break
        except Exception:
            time.sleep(0.3)
            continue
        time.sleep(0.3)
    if phase != "waiting_primary":
        raise AssertionError(f"Workflow did not reach waiting_primary (phase={phase!r})")

    pending = [row for row in list_inbox() if row["workflow_id"] == wf_id]
    if not pending or pending[0]["status"] != "waiting_primary":
        raise AssertionError(f"Inbox did not show a pending approval: {pending}")
    if get_execution(key) is not None:
        raise AssertionError("Side effect ran before anyone approved")

    return {"proposal": proposal, "workflow_id": wf_id, "start": start}


def main() -> int:
    print("=== Approval gate crash test ===")
    base = Path(tempfile.mkdtemp(prefix="approval-gate-crash-"))
    stack = Stack(base)
    print(f"Temp dir: {base}")
    print(f"Temporal port: {stack.port}")
    try:
        print("Starting Temporal dev server…")
        stack.start_server()
        _prepare_imports(stack.env)
        # Imports happen after env is set.
        from approvalgate.client import (
            get_snapshot,
            signal_decision,
            start_proposal,
            wait_for_result,
        )
        from approvalgate.samples import refund_2400
        from approvalgate.store import execute_once, get_execution, list_inbox

        print("Starting worker…")
        stack.start_worker()

        proposal = refund_2400()
        key = proposal.idempotency_key
        print(f"Submitting $2,400 refund (idempotency key {key})…")
        start = start_proposal(proposal)
        wf_id = start["workflow_id"]
        print(f"Workflow id: {wf_id}")

        deadline = time.time() + 25
        phase = None
        while time.time() < deadline:
            try:
                snap = get_snapshot(wf_id)
                phase = snap.get("status")
                if phase == "waiting_primary":
                    break
            except Exception:
                time.sleep(0.25)
                continue
            time.sleep(0.25)
        if phase != "waiting_primary":
            raise SystemExit(f"FAIL: never reached waiting_primary (status={phase!r})")
        print("Workflow is waiting for a human (Desk Manager / Controller).")
        if get_execution(key) is not None:
            raise SystemExit("FAIL: side effect ran before approval")

        print("Killing the worker mid-wait (SIGKILL)…")
        stack.kill_worker()
        time.sleep(0.4)

        # The server should still describe the workflow as running.
        # Queries need a worker, so we only check that the process is gone
        # and that the side effect still has not run.
        if stack.worker and stack.worker.poll() is None:
            raise SystemExit("FAIL: worker is still running after SIGKILL")
        if get_execution(key) is not None:
            raise SystemExit("FAIL: side effect ran while the worker was dead")
        print("Worker is dead. Refund has not been issued. Restarting the worker…")

        stack.start_worker()
        snap = None
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                snap = get_snapshot(wf_id)
                if snap.get("status") == "waiting_primary":
                    break
            except Exception:
                time.sleep(0.25)
                continue
            time.sleep(0.25)
        if not snap or snap.get("status") != "waiting_primary":
            raise SystemExit(f"FAIL: after restart, status was {snap}")
        if get_execution(key) is not None:
            raise SystemExit("FAIL: restart re-executed the action")
        print("After restart, the same workflow is still waiting. No refund was issued.")

        print("Sending Approve as Pat Kim, Controller…")
        signal_decision(wf_id, "approve", "Pat Kim", "Controller", "Okay to refund — documented comeback.")
        result = wait_for_result(wf_id, timeout=20)
        status = result.get("status")
        if status != "approved":
            raise SystemExit(f"FAIL: expected approved, got {result}")
        execution = get_execution(key)
        if not execution:
            raise SystemExit("FAIL: approved but no execution row")
        if int(execution["attempt_count"]) != 1:
            raise SystemExit(f"FAIL: expected 1 attempt, got {execution['attempt_count']}")
        print(f"Executed once: {execution['result']}")

        print("Sending a second Approve (should not refund twice)…")
        try:
            signal_decision(wf_id, "approve", "Pat Kim", "Controller", "Clicked again by mistake.")
        except Exception as exc:
            # A completed workflow will not accept another signal. That is
            # expected — the first decision already closed it.
            print(f"Second signal was rejected by Temporal ({type(exc).__name__}); that is expected after completion.")
        time.sleep(0.4)
        again = execute_once(
            idempotency_key=key,
            workflow_id=wf_id,
            action_type="customer_refund",
            result="should-not-replace",
        )
        execution = get_execution(key)
        if again["first_time"] or int(execution["attempt_count"]) < 2:
            raise SystemExit(f"FAIL: idempotency did not hold: {again} {execution}")
        if execution["result"] == "should-not-replace":
            raise SystemExit("FAIL: the original result was overwritten")
        print(
            f"Second approve / replay did not issue another refund "
            f"(attempt_count={execution['attempt_count']}, original result kept)."
        )

        print("PASS: worker crash was survived, and the refund ran exactly once.")

        print("Submitting a short-timeout refund to prove auto-reject…")
        from approvalgate.samples import short_timeout_refund

        timed = short_timeout_refund()
        timed.timeout_seconds = 2
        timed.escalation_timeout_seconds = 2
        timed_start = start_proposal(timed)
        timed_id = timed_start["workflow_id"]
        timed_result = wait_for_result(timed_id, timeout=20)
        if timed_result.get("status") != "timed_out":
            raise SystemExit(f"FAIL: expected timed_out, got {timed_result}")
        if get_execution(timed.idempotency_key) is not None:
            raise SystemExit("FAIL: a timed-out action was executed")
        print("PASS: after escalation timed out, the action was auto-rejected and did not run.")
        print(f"Inbox after test: {sorted({r['status'] for r in list_inbox()})}")
        return 0
    except Exception:
        print("---- temporal.log (tail) ----")
        log = base / "temporal.log"
        if log.exists():
            print(log.read_text()[-3000:])
        print("---- worker.log (tail) ----")
        wlog = base / "worker.log"
        if wlog.exists():
            print(wlog.read_text()[-3000:])
        raise
    finally:
        stack.stop()
        print(f"Cleaned up. Logs left in {base} if you want them.")


if __name__ == "__main__":
    raise SystemExit(main())
