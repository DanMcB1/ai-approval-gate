"""SQLite audit log, mock Slack inbox, and idempotent action execution.

Temporal is the source of truth for workflow state. This database is the
human-readable trail and the guard that makes the *final side effect*
run at most once, even if an activity is retried.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from approvalgate.settings import db_path as default_db_path

_LOCAL = threading.local()


def _connect(path: Path | None = None) -> sqlite3.Connection:
    target = Path(path or default_db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def connection(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS inbox (
    workflow_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    action_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    reason TEXT NOT NULL,
    department TEXT NOT NULL,
    store TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    amount_usd REAL,
    recipient_count INTEGER,
    primary_role TEXT,
    escalation_role TEXT,
    policy_reason TEXT,
    risk TEXT,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS executions (
    idempotency_key TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    result TEXT NOT NULL,
    first_executed_at TEXT NOT NULL,
    last_attempted_at TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1
);
"""


def init_db(path: Path | None = None) -> None:
    with connection(path) as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_event(
    *,
    workflow_id: str,
    idempotency_key: str,
    event_type: str,
    actor: str,
    actor_role: str,
    message: str,
    payload: dict[str, Any] | None = None,
    path: Path | None = None,
) -> int:
    init_db(path)
    ts = _now()
    with connection(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO audit_events (
                ts, workflow_id, idempotency_key, event_type, actor, actor_role, message, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                workflow_id,
                idempotency_key,
                event_type,
                actor,
                actor_role,
                message,
                json.dumps(payload or {}, default=str),
            ),
        )
        return int(cur.lastrowid)


def upsert_inbox(row: dict[str, Any], path: Path | None = None) -> None:
    init_db(path)
    now = _now()
    with connection(path) as conn:
        existing = conn.execute(
            "SELECT created_at FROM inbox WHERE workflow_id = ?",
            (row["workflow_id"],),
        ).fetchone()
        created = existing["created_at"] if existing else now
        conn.execute(
            """
            INSERT INTO inbox (
                workflow_id, idempotency_key, action_type, title, summary, reason,
                department, store, requested_by, amount_usd, recipient_count,
                primary_role, escalation_role, policy_reason, risk, phase, status,
                created_at, updated_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                phase=excluded.phase,
                status=excluded.status,
                primary_role=excluded.primary_role,
                escalation_role=excluded.escalation_role,
                updated_at=excluded.updated_at,
                payload_json=excluded.payload_json
            """,
            (
                row["workflow_id"],
                row["idempotency_key"],
                row["action_type"],
                row["title"],
                row["summary"],
                row.get("reason", ""),
                row.get("department", ""),
                row.get("store", ""),
                row.get("requested_by", ""),
                row.get("amount_usd"),
                row.get("recipient_count"),
                row.get("primary_role"),
                row.get("escalation_role"),
                row.get("policy_reason", ""),
                row.get("risk", ""),
                row["phase"],
                row["status"],
                created,
                now,
                json.dumps(row.get("payload") or {}, default=str),
            ),
        )


def list_inbox(status: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    init_db(path)
    with connection(path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM inbox WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM inbox ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def list_audit(limit: int = 200, workflow_id: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    init_db(path)
    with connection(path) as conn:
        if workflow_id:
            rows = conn.execute(
                "SELECT * FROM audit_events WHERE workflow_id = ? ORDER BY id DESC LIMIT ?",
                (workflow_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.pop("payload_json") or "{}")
            except json.JSONDecodeError:
                item["payload"] = {}
            out.append(item)
        return out


def workflow_rows(path: Path | None = None) -> list[dict[str, Any]]:
    """Dashboard rows: one per workflow, latest inbox state plus first event time."""
    init_db(path)
    with connection(path) as conn:
        rows = conn.execute(
            """
            SELECT i.*,
                   (SELECT COUNT(*) FROM executions e WHERE e.idempotency_key = i.idempotency_key) AS executed
            FROM inbox i
            ORDER BY i.updated_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def execute_once(
    *,
    idempotency_key: str,
    workflow_id: str,
    action_type: str,
    result: str,
    path: Path | None = None,
) -> dict[str, Any]:
    """Apply the side effect at most once.

    The first call inserts a row and returns first_time=True.
    Later calls (activity retries, duplicate signals, a replayed workflow)
    increment attempt_count and return first_time=False with the original result.
    """
    init_db(path)
    now = _now()
    with connection(path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO executions (
                    idempotency_key, workflow_id, action_type, result,
                    first_executed_at, last_attempted_at, attempt_count
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (idempotency_key, workflow_id, action_type, result, now, now),
            )
            return {
                "idempotency_key": idempotency_key,
                "first_time": True,
                "attempt_count": 1,
                "result": result,
                "first_executed_at": now,
            }
        except sqlite3.IntegrityError:
            conn.execute(
                """
                UPDATE executions
                SET last_attempted_at = ?, attempt_count = attempt_count + 1
                WHERE idempotency_key = ?
                """,
                (now, idempotency_key),
            )
            row = conn.execute(
                "SELECT * FROM executions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            data = dict(row)
            return {
                "idempotency_key": idempotency_key,
                "first_time": False,
                "attempt_count": int(data["attempt_count"]),
                "result": data["result"],
                "first_executed_at": data["first_executed_at"],
            }


def get_execution(idempotency_key: str, path: Path | None = None) -> dict[str, Any] | None:
    init_db(path)
    with connection(path) as conn:
        row = conn.execute(
            "SELECT * FROM executions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return dict(row) if row else None


def counts(path: Path | None = None) -> dict[str, int]:
    init_db(path)
    with connection(path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM inbox GROUP BY status"
        ).fetchall()
        out = {"pending": 0, "approved": 0, "auto_approved": 0, "rejected": 0, "timed_out": 0}
        for row in rows:
            status = row["status"]
            if status in {"waiting_primary", "escalated"}:
                out["pending"] += row["n"]
            elif status in out:
                out[status] += row["n"]
            elif status == "auto_approved":
                out["auto_approved"] += row["n"]
        out["executed"] = int(
            conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
        )
        return out
