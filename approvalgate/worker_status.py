"""Best-effort check for a locally started worker process."""

from __future__ import annotations

import os
from pathlib import Path

from approvalgate.settings import data_dir


def worker_seems_running() -> bool:
    pid_path = Path(os.environ.get("APPROVAL_GATE_WORKER_PID", data_dir() / "worker.pid"))
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text().strip())
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
