"""Paths, ports, and task-queue names. Read from the environment at call time."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    path = Path(os.environ.get("APPROVAL_GATE_DATA", ROOT / "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return Path(os.environ.get("APPROVAL_GATE_DB", data_dir() / "approval_gate.db"))


def temporal_db() -> Path:
    return Path(os.environ.get("TEMPORAL_DB", data_dir() / "temporal.db"))


def temporal_address() -> str:
    return os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233")


def temporal_namespace() -> str:
    return os.environ.get("TEMPORAL_NAMESPACE", "default")


def task_queue() -> str:
    return os.environ.get("APPROVAL_GATE_TASK_QUEUE", "approval-gate")


def temporal_port() -> int:
    return int(os.environ.get("TEMPORAL_PORT", "7233"))


def temporal_ui_port() -> int:
    return int(os.environ.get("TEMPORAL_UI_PORT", "8233"))


def temporal_http_port() -> int:
    return int(os.environ.get("TEMPORAL_HTTP_PORT", "7243"))


def temporal_metrics_port() -> int:
    return int(os.environ.get("TEMPORAL_METRICS_PORT", "7253"))


def slack_enabled() -> bool:
    return os.environ.get("APPROVAL_GATE_SLACK_ENABLED", "").lower() in {"1", "true", "yes"}


def slack_bot_token() -> str:
    return os.environ.get("SLACK_BOT_TOKEN", "").strip()


def slack_signing_secret() -> str:
    return os.environ.get("SLACK_SIGNING_SECRET", "").strip()


def slack_channel() -> str:
    return os.environ.get("SLACK_APPROVAL_CHANNEL", "").strip()


COMPANY = "Lakeside Auto Group (sample)"
