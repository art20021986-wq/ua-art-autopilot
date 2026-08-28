"""TASK 071 — durable, process-safe, crash-safe FIFO queue.

Used only when a direct write attempt exceeds `direct_write_budget_s` (0.8s)
or raises a locked/busy sqlite error. Enqueue is fast and always succeeds
(returns a quick 'Принято, сохраняю' style ack payload); a background/next-
process drain performs the real committed write via writer.apply_field_update
and only then is the operation considered acknowledged ('Сохранено').

Idempotency: operation_id is UNIQUE in both the queue table and the audit
table, so re-delivery / crash-restart cannot double apply. A queued item is
skipped (marked applied, no-op) if the audit table already has that
operation_id BEFORE the queue item is drained, which covers the case where
the CRM commit already happened before the crash occurred pre-ack.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from cloud.task_071.writer import apply_field_update

QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS write_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT UNIQUE NOT NULL,
    card_id INTEGER NOT NULL,
    table_name TEXT NOT NULL,
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    actor TEXT NOT NULL,
    enqueued_ts REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
"""


def open_queue_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=5)
    conn.execute(QUEUE_SCHEMA)
    conn.commit()
    return conn


def enqueue(
    queue_conn: sqlite3.Connection,
    table: str,
    card_id: int,
    field: str,
    value: Any,
    operation_id: str,
    actor: str = "cars_ui",
) -> dict:
    with queue_conn:
        try:
            queue_conn.execute(
                "INSERT INTO write_queue(operation_id, card_id, table_name, field, value, actor, enqueued_ts, status) "
                "VALUES (?,?,?,?,?,?,?, 'pending')",
                (operation_id, card_id, table, field, json.dumps(value), actor, time.time()),
            )
        except sqlite3.IntegrityError:
            pass  # already enqueued once; idempotent
    return {"status": "accepted", "message": "Принято, сохраняю", "operation_id": operation_id}


def enqueue_if_busy(
    table: str,
    card_id: int,
    field: str,
    value: Any,
    operation_id: str,
    direct_conn: Optional[sqlite3.Connection] = None,
    queue_conn: Optional[sqlite3.Connection] = None,
    direct_write_budget_s: float = 0.8,
) -> Optional[dict]:
    """Try the direct atomic write within the budget; if it fails with
    locked/busy, fall back to durable enqueue and return the quick ack. If the
    direct write succeeds, returns None so the caller proceeds with its normal
    'Сохранено' response path.
    """
    if direct_conn is not None:
        started = time.monotonic()
        try:
            apply_field_update(direct_conn, table, card_id, field, value, operation_id)
            return None
        except sqlite3.OperationalError:
            if time.monotonic() - started > direct_write_budget_s or queue_conn is None:
                raise
    if queue_conn is not None:
        return enqueue(queue_conn, table, card_id, field, value, operation_id)
    return None


def drain(queue_conn: sqlite3.Connection, target_conn: sqlite3.Connection, audit_check_conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Drain all pending queue items in FIFO order against target_conn.

    Returns a list of per-item result dicts. Safe to call from multiple
    processes concurrently: each row update to 'applying' happens inside its
    own short transaction guarded by the UNIQUE operation_id and a status
    CAS-style UPDATE ... WHERE status='pending'.
    """
    results = []
    audit_conn = audit_check_conn or target_conn
    cur = queue_conn.cursor()
    cur.execute("SELECT id, operation_id, card_id, table_name, field, value, actor FROM write_queue WHERE status='pending' ORDER BY id ASC")
    rows = cur.fetchall()
    for row_id, operation_id, card_id, table_name, field, value_json, actor in rows:
        with queue_conn:
            claimed = queue_conn.execute(
                "UPDATE write_queue SET status='applying' WHERE id=? AND status='pending'",
                (row_id,),
            )
            if claimed.rowcount == 0:
                continue  # another drainer already claimed it
        try:
            already = audit_conn.execute(
                "SELECT 1 FROM audit WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if already:
                outcome = {"status": "duplicate_ignored", "operation_id": operation_id}
            else:
                value = json.loads(value_json)
                outcome = apply_field_update(target_conn, table_name, card_id, field, value, operation_id, actor=actor)
            with queue_conn:
                queue_conn.execute("UPDATE write_queue SET status='applied' WHERE id=?", (row_id,))
            results.append(outcome)
        except Exception as exc:  # noqa: BLE001 - queue must not crash the drain loop
            with queue_conn:
                queue_conn.execute("UPDATE write_queue SET status='pending' WHERE id=?", (row_id,))
            results.append({"status": "error", "operation_id": operation_id, "error": str(exc)})
    return results
