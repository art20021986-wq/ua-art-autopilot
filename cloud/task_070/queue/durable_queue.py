"""Process-safe durable FIFO queue for deferred CRM writes.

Backed by its own SQLite file (separate from crm.db) so queue writes never
compete with the card database for locks. Atomic enqueue/claim/ack/requeue,
WAL + fsync (synchronous=FULL), UNIQUE(operation_id) so retries are
idempotent, and a claim ttl so a crashed drainer's item becomes reclaimable.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT UNIQUE NOT NULL,
    auto_number TEXT NOT NULL,
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT 'cars',
    actor TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    claimed_at REAL,
    claimed_by TEXT,
    acked_at REAL,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status, id);
"""

CLAIM_TTL_SECONDS = 10.0
_lock = threading.Lock()


@dataclass
class QueueItem:
    id: int
    operation_id: str
    auto_number: str
    field: str
    value: str
    entity: str
    actor: Optional[str]
    attempts: int


class DurableQueue:
    _default_instance = None

    def __init__(self, path: str = "crm_write_queue.db"):
        self.path = path
        self._init_schema()

    @classmethod
    def default(cls) -> "DurableQueue":
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def enqueue(self, auto_number, field, value, entity="cars", actor=None,
                operation_id: Optional[str] = None) -> str:
        operation_id = operation_id or str(uuid.uuid4())
        with _lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO queue_items "
                    "(operation_id, auto_number, field, value, entity, actor, status, created_at) "
                    "VALUES (?,?,?,?,?,?, 'pending', ?)",
                    (operation_id, auto_number, field, str(value), entity, actor, time.time()),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return operation_id

    def claim(self, worker_id: str) -> Optional[QueueItem]:
        now = time.time()
        with _lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT id, operation_id, auto_number, field, value, entity, actor, attempts "
                    "FROM queue_items WHERE status='pending' "
                    "OR (status='claimed' AND claimed_at < ?) "
                    "ORDER BY id ASC LIMIT 1",
                    (now - CLAIM_TTL_SECONDS,),
                ).fetchone()
                if row is None:
                    conn.execute("COMMIT")
                    return None
                item_id = row[0]
                conn.execute(
                    "UPDATE queue_items SET status='claimed', claimed_at=?, claimed_by=?, "
                    "attempts=attempts+1 WHERE id=?",
                    (now, worker_id, item_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return QueueItem(
            id=row[0], operation_id=row[1], auto_number=row[2], field=row[3],
            value=row[4], entity=row[5], actor=row[6], attempts=row[7] + 1,
        )

    def ack(self, item_id: int):
        with _lock, self._connect() as conn:
            conn.execute("UPDATE queue_items SET status='done', acked_at=? WHERE id=?",
                         (time.time(), item_id))

    def requeue(self, item_id: int):
        with _lock, self._connect() as conn:
            conn.execute(
                "UPDATE queue_items SET status='pending', claimed_at=NULL, claimed_by=NULL "
                "WHERE id=?", (item_id,))

    def depth(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM queue_items WHERE status IN ('pending','claimed')"
            ).fetchone()
            return row[0]

    def oldest_age_seconds(self) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MIN(created_at) FROM queue_items WHERE status IN ('pending','claimed')"
            ).fetchone()
            if row is None or row[0] is None:
                return 0.0
            return time.time() - row[0]


def drain_once(queue: DurableQueue, apply_fn, worker_id: str = "drainer") -> int:
    """Claims and applies items until the queue is empty or apply_fn raises
    a transient error. Returns number of items successfully acked.
    apply_fn(item_dict) must be idempotent (see writer.safe_writer.replay_from_queue).
    """
    acked = 0
    while True:
        item = queue.claim(worker_id)
        if item is None:
            break
        try:
            apply_fn({
                "operation_id": item.operation_id,
                "auto_number": item.auto_number,
                "field": item.field,
                "value": item.value,
                "entity": item.entity,
                "actor": item.actor,
            })
            queue.ack(item.id)
            acked += 1
        except Exception:
            queue.requeue(item.id)
            break
    return acked
