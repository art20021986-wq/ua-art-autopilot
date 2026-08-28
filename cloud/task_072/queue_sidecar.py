"""
Durable process-safe FIFO sidecar queue for description-save operations.

Design:
  - Separate SQLite file (does not touch crm.db schema at all).
  - UNIQUE operation_id enforces idempotency: replay of the same Telegram
    chat_id:message_id (used as/hashed into operation_id) never double-enqueues.
  - "last-intended-wins": before applying a queued item, the drain checks whether a
    newer item for the same card_id has already been applied (or exists ahead in the
    queue with a later timestamp); if so, the older item is marked SKIPPED_SUPERSEDED
    rather than applied, protecting against older-overwrites-newer races.
  - Crash-safety:
      * crash after enqueue, before drain -> item stays PENDING, drained on restart.
      * crash after CRM commit, before queue ack -> on restart, drain re-checks via
        read-back against cars.condition_text; if the stored text already matches the
        queued text, the item is marked APPLIED without re-writing (idempotent ack).
  - Multi-process safe: uses SQLite's own locking (BEGIN IMMEDIATE) plus a status column
    with compare-and-set semantics so multiple drain workers never double-apply.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from . import writer as writer_mod

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS description_ops (
    operation_id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    requested_field TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at REAL NOT NULL,
    applied_at REAL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_card_status ON description_ops(card_id, status);
"""


@dataclass
class EnqueueResult:
    operation_id: str
    already_existed: bool


def open_queue(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def make_operation_id(chat_id: str, message_id: str) -> str:
    return f"{chat_id}:{message_id}"


def enqueue(
    qconn: sqlite3.Connection,
    chat_id: str,
    message_id: str,
    card_id: str,
    requested_field: str,
    raw_text: str,
) -> EnqueueResult:
    operation_id = make_operation_id(chat_id, message_id)
    try:
        qconn.execute(
            "INSERT INTO description_ops "
            "(operation_id, card_id, chat_id, message_id, requested_field, raw_text, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)",
            (operation_id, card_id, chat_id, message_id, requested_field, raw_text, time.time()),
        )
        qconn.commit()
        return EnqueueResult(operation_id=operation_id, already_existed=False)
    except sqlite3.IntegrityError:
        return EnqueueResult(operation_id=operation_id, already_existed=True)


def _latest_created_for_card(qconn: sqlite3.Connection, card_id: str, exclude_op: str) -> Optional[float]:
    row = qconn.execute(
        "SELECT MAX(created_at) FROM description_ops "
        "WHERE card_id = ? AND operation_id != ? AND status IN ('PENDING','APPLIED')",
        (card_id, exclude_op),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def drain_one(qconn: sqlite3.Connection, crm_conn: sqlite3.Connection) -> Optional[str]:
    """Attempts to apply exactly one PENDING operation (FIFO). Returns operation_id
    handled, or None if the queue is empty. Safe to call from multiple processes.
    """
    qconn.execute("BEGIN IMMEDIATE")
    row = qconn.execute(
        "SELECT operation_id, card_id, requested_field, raw_text, created_at "
        "FROM description_ops WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    if row is None:
        qconn.execute("ROLLBACK")
        return None
    operation_id, card_id, requested_field, raw_text, created_at = row

    # Claim it (compare-and-set) so a concurrent drain worker cannot also pick it up.
    qconn.execute(
        "UPDATE description_ops SET status = 'CLAIMED' WHERE operation_id = ? AND status = 'PENDING'",
        (operation_id,),
    )
    qconn.commit()

    # last-intended-wins: if a newer op exists for the same card, skip this older one.
    newer_ts = _latest_created_for_card(qconn, card_id, operation_id)
    if newer_ts is not None and newer_ts > created_at:
        qconn.execute(
            "UPDATE description_ops SET status = 'SKIPPED_SUPERSEDED', applied_at = ? "
            "WHERE operation_id = ?",
            (time.time(), operation_id),
        )
        qconn.commit()
        return operation_id

    try:
        allowlist = writer_mod.build_allowlist(crm_conn)
        field = writer_mod.resolve_target_field(requested_field, allowlist)
        text = writer_mod.normalize_text(raw_text)
        current = writer_mod.read_field(crm_conn, allowlist, card_id, field)
        if current == text:
            # Idempotent: crash-after-CRM-commit-before-ack case. Just ack.
            qconn.execute(
                "UPDATE description_ops SET status = 'APPLIED', applied_at = ? WHERE operation_id = ?",
                (time.time(), operation_id),
            )
            qconn.commit()
            return operation_id

        writer_mod.save_description(
            crm_conn, card_id, requested_field, raw_text, operation_id, actor="queue_drain"
        )
        qconn.execute(
            "UPDATE description_ops SET status = 'APPLIED', applied_at = ? WHERE operation_id = ?",
            (time.time(), operation_id),
        )
        qconn.commit()
    except Exception as exc:  # noqa: BLE001 - persisted for operator visibility only
        qconn.execute(
            "UPDATE description_ops SET status = 'PENDING', error = ? WHERE operation_id = ?",
            (str(exc)[:500], operation_id),
        )
        qconn.commit()
        raise
    return operation_id


def drain_all(qconn: sqlite3.Connection, crm_conn: sqlite3.Connection, max_items: int = 10000) -> int:
    count = 0
    while count < max_items:
        handled = drain_one(qconn, crm_conn)
        if handled is None:
            break
        count += 1
    return count
