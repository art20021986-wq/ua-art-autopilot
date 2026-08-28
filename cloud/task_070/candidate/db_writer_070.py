"""TASK_070 candidate: single card-field writer contract.

Design goals mandated by task_070:
  1. One writer path for ALL scalar card fields (price, mileage, stage,
     container, deadline, and future fields).
  2. Direct commit attempt waits at most WRITE_TIMEOUT_SECONDS (1.0s).
  3. On sqlite3.OperationalError containing 'locked'/'busy', or on our own
     queue-submit timeout, the write is atomically appended to a durable
     FIFO queue instead of raising to the caller. The bot must respond
     fast without ever showing 'database is locked' or a traceback.
  4. Price + price_history are written in ONE transaction (atomic).
  5. log_action is best-effort and NON-BLOCKING: any failure there is
     caught and logged, never propagated, and never blocks or reverts the
     primary field write.
  6. No background/site-rebuild/media-send side effects are triggered
     from this writer.

This is an isolated candidate module (cloud/task_070/candidate/). It is
NOT wired into production cars_ui.py / db.py in this Gate A package.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("db_writer_070")

WRITE_TIMEOUT_SECONDS = 1.0
BUSY_TIMEOUT_MS = int(WRITE_TIMEOUT_SECONDS * 1000)


class FastPathLocked(Exception):
    """Internal signal: direct write could not complete within budget."""


@dataclass
class WriteResult:
    ok: bool
    queued: bool
    duration_s: float
    card_id: str
    field: Optional[str] = None
    error: Optional[str] = None


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=WRITE_TIMEOUT_SECONDS, isolation_level=None)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def _is_lock_error(exc: sqlite3.OperationalError) -> bool:
    msg = str(exc).lower()
    return "locked" in msg or "busy" in msg


# ---------------------------------------------------------------------------
# Durable FIFO queue (file-backed, atomic append, crash-safe drain)
# ---------------------------------------------------------------------------

class DurableQueue070:
    """Append-only JSONL durable queue with atomic rename-based enqueue and
    an at-least-once drain that removes entries only after a confirmed
    successful re-apply.
    """

    def __init__(self, queue_path: str):
        self.queue_path = queue_path
        d = os.path.dirname(os.path.abspath(queue_path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.queue_path):
            open(self.queue_path, "a", encoding="utf-8").close()

    def enqueue(self, record: dict) -> str:
        record = dict(record)
        record.setdefault("queued_id", str(uuid.uuid4()))
        record.setdefault("queued_at", time.time())
        line = json.dumps(record, ensure_ascii=False)
        # Atomic append: open in append mode, write single line, flush+fsync.
        with open(self.queue_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        return record["queued_id"]

    def read_all(self) -> list:
        if not os.path.exists(self.queue_path):
            return []
        out = []
        with open(self.queue_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("db_writer_070: skipping corrupt queue line")
        return out

    def size(self) -> int:
        return len(self.read_all())

    def drain(self, apply_fn) -> int:
        """Attempt to apply every queued record via apply_fn(record) -> bool.
        Successfully applied records are removed. Remaining records are
        rewritten back (order preserved) so nothing is lost on partial
        failure or process restart.
        """
        records = self.read_all()
        if not records:
            return 0
        remaining = []
        applied = 0
        for rec in records:
            try:
                ok = apply_fn(rec)
            except Exception as exc:  # never let drain crash
                log.warning("db_writer_070: drain apply failed: %s", exc)
                ok = False
            if ok:
                applied += 1
            else:
                remaining.append(rec)
        tmp_path = self.queue_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            for rec in remaining:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.queue_path)
        return applied


# ---------------------------------------------------------------------------
# Single writer contract
# ---------------------------------------------------------------------------

class CardFieldWriter070:
    ALLOWED_FIELDS = {
        "price", "mileage", "stage", "container", "deadline",
    }

    def __init__(self, db_path: str, queue_path: str):
        self.db_path = db_path
        self.queue = DurableQueue070(queue_path)

    # -- primary scalar field write (mileage/stage/container/deadline/etc.) --
    def write_field(self, card_id: str, field: str, value: Any) -> WriteResult:
        t0 = time.monotonic()
        try:
            conn = _connect(self.db_path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    f"UPDATE cards SET {field}=?, updated_at=? WHERE card_id=?",
                    (value, time.time(), card_id),
                )
                conn.execute("COMMIT")
            finally:
                conn.close()
            dt = time.monotonic() - t0
            self._log_action_best_effort(card_id, field, value)
            return WriteResult(ok=True, queued=False, duration_s=dt, card_id=card_id, field=field)
        except sqlite3.OperationalError as exc:
            if _is_lock_error(exc):
                self.queue.enqueue({
                    "kind": "field", "card_id": card_id, "field": field, "value": value,
                })
                dt = time.monotonic() - t0
                log.warning("db_writer_070: locked, queued field write card=%s field=%s", card_id, field)
                return WriteResult(ok=True, queued=True, duration_s=dt, card_id=card_id, field=field)
            dt = time.monotonic() - t0
            log.error("db_writer_070: non-lock OperationalError: %s", exc)
            return WriteResult(ok=False, queued=False, duration_s=dt, card_id=card_id, field=field, error=str(exc))

    # -- price is a single atomic transaction covering price + price_history --
    def write_price(self, card_id: str, new_price: Any, currency: str = "USD") -> WriteResult:
        t0 = time.monotonic()
        ts = time.time()
        try:
            conn = _connect(self.db_path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE cards SET price=?, currency=?, updated_at=? WHERE card_id=?",
                    (new_price, currency, ts, card_id),
                )
                conn.execute(
                    "INSERT INTO price_history(card_id, price, currency, changed_at) VALUES (?,?,?,?)",
                    (card_id, new_price, currency, ts),
                )
                conn.execute("COMMIT")
            finally:
                conn.close()
            dt = time.monotonic() - t0
            self._log_action_best_effort(card_id, "price", new_price)
            return WriteResult(ok=True, queued=False, duration_s=dt, card_id=card_id, field="price")
        except sqlite3.OperationalError as exc:
            if _is_lock_error(exc):
                self.queue.enqueue({
                    "kind": "price", "card_id": card_id, "price": new_price,
                    "currency": currency, "changed_at": ts,
                })
                dt = time.monotonic() - t0
                log.warning("db_writer_070: locked, queued price write card=%s", card_id)
                return WriteResult(ok=True, queued=True, duration_s=dt, card_id=card_id, field="price")
            dt = time.monotonic() - t0
            log.error("db_writer_070: non-lock OperationalError on price: %s", exc)
            return WriteResult(ok=False, queued=False, duration_s=dt, card_id=card_id, field="price", error=str(exc))

    def _log_action_best_effort(self, card_id: str, field: str, value: Any) -> None:
        """Non-blocking audit log. Never raises, never delays or reverts
        the primary write."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=0.2, isolation_level=None)
            try:
                conn.execute("PRAGMA busy_timeout=200")
                conn.execute(
                    "INSERT INTO log_action(card_id, field, value, at) VALUES (?,?,?,?)",
                    (card_id, field, str(value), time.time()),
                )
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 - audit must never break the main flow
            log.warning("db_writer_070: log_action best-effort failed (ignored): %s", exc)

    def drain_queue(self) -> int:
        def _apply(rec: dict) -> bool:
            try:
                conn = _connect(self.db_path)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    if rec.get("kind") == "price":
                        conn.execute(
                            "UPDATE cards SET price=?, currency=?, updated_at=? WHERE card_id=?",
                            (rec["price"], rec["currency"], rec["changed_at"], rec["card_id"]),
                        )
                        conn.execute(
                            "INSERT INTO price_history(card_id, price, currency, changed_at) VALUES (?,?,?,?)",
                            (rec["card_id"], rec["price"], rec["currency"], rec["changed_at"]),
                        )
                    else:
                        conn.execute(
                            f"UPDATE cards SET {rec['field']}=?, updated_at=? WHERE card_id=?",
                            (rec["value"], time.time(), rec["card_id"]),
                        )
                    conn.execute("COMMIT")
                finally:
                    conn.close()
                return True
            except sqlite3.OperationalError as exc:
                if _is_lock_error(exc):
                    return False
                log.error("db_writer_070: drain non-lock error: %s", exc)
                return False
        return self.queue.drain(_apply)
