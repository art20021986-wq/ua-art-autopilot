#!/usr/bin/env python3
"""Atomic, durable writer for CRM marketing descriptions (TASK 072).

The public entry point is ``save_or_enqueue``.  It always targets the existing
``cars.id`` row and the canonical ``cars.condition_text`` column.  It never
creates a car and never writes the diagnostic or legacy description columns.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any


CANONICAL_FIELD = "condition_text"
MIN_LENGTH = 1
MAX_LENGTH = 12_000
DIRECT_TIMEOUT_SECONDS = 0.45
QUEUE_TIMEOUT_SECONDS = 2.0
WORK_LEASE_SECONDS = 15.0
STALE_OPERATION_SECONDS = 45.0

_THREAD_GUARD = threading.Lock()
_WORKERS: set[str] = set()


class DescriptionError(RuntimeError):
    """Base error safe for caller-side classification."""


class DescriptionValidationError(DescriptionError):
    pass


class CardNotFoundError(DescriptionError):
    pass


class SchemaMismatchError(DescriptionError):
    pass


class ReadbackMismatchError(DescriptionError):
    pass


class CrmBusyError(DescriptionError):
    pass


QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS description_ops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    card_id INTEGER NOT NULL,
    actor_id INTEGER,
    description_text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    claimed_at REAL,
    applied_at REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_description_ops_pending
    ON description_ops(status, id);
CREATE INDEX IF NOT EXISTS idx_description_ops_card
    ON description_ops(card_id, id);
CREATE TABLE IF NOT EXISTS description_worker_lease (
    name TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    lease_until REAL NOT NULL
);
"""


def normalize_text(raw: str) -> str:
    """Normalize transport newlines while retaining the user's internal layout."""
    if raw is None:
        raise DescriptionValidationError("empty")
    if not isinstance(raw, str):
        raw = str(raw)
    text = raw.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    # Telegram already trims the message.  This only removes accidental blank
    # lines around it; spaces and all line breaks inside remain untouched.
    text = text.strip("\n")
    if not text.strip():
        raise DescriptionValidationError("empty")
    if len(text) > MAX_LENGTH:
        raise DescriptionValidationError("too_long")
    return text


def _operation_id(value: str) -> str:
    value = str(value or "").strip()
    if not value or len(value) > 200:
        raise DescriptionValidationError("operation_id")
    return value


def _card_id(value: Any) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise DescriptionValidationError("card_id") from exc
    if result <= 0:
        raise DescriptionValidationError("card_id")
    return result


def _actor_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(%s)" % table)}


def _assert_live_schema(conn: sqlite3.Connection) -> bool:
    cars = _table_columns(conn, "cars")
    audit = _table_columns(conn, "audit")
    required_cars = {"id", CANONICAL_FIELD}
    required_audit = {
        "actor_id", "action", "entity_type", "entity_id", "field",
        "old_value", "new_value", "created_at",
    }
    if not required_cars.issubset(cars):
        raise SchemaMismatchError("cars_schema")
    if not required_audit.issubset(audit):
        raise SchemaMismatchError("audit_schema")
    return "updated_at" in cars


def _connect_crm(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(
        db_path,
        timeout=DIRECT_TIMEOUT_SECONDS,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=%d" % int(DIRECT_TIMEOUT_SECONDS * 1000))
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _is_busy(exc: BaseException) -> bool:
    message = str(exc).casefold()
    return "locked" in message or "busy" in message


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _atomic_write(
    db_path: str,
    card_id: int,
    text: str,
    actor_id: int | None,
) -> dict[str, Any]:
    """Update + audit in one SQLite transaction and verify exact read-back."""
    conn = _connect_crm(db_path)
    committed = False
    try:
        has_updated_at = _assert_live_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT condition_text FROM cars WHERE id=?", (card_id,)
        ).fetchone()
        if row is None:
            raise CardNotFoundError("missing_card")
        old_value = row[0]
        changed = old_value != text
        if changed:
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if has_updated_at:
                cursor = conn.execute(
                    "UPDATE cars SET condition_text=?, updated_at=? WHERE id=?",
                    (text, timestamp, card_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE cars SET condition_text=? WHERE id=?", (text, card_id)
                )
            if cursor.rowcount != 1:
                raise CardNotFoundError("missing_card")
            conn.execute(
                "INSERT INTO audit "
                "(actor_id, action, entity_type, entity_id, field, old_value, new_value, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    actor_id,
                    "card_edit",
                    "cars",
                    card_id,
                    CANONICAL_FIELD,
                    str(old_value) if old_value is not None else None,
                    text,
                    timestamp,
                ),
            )
        conn.execute("COMMIT")
        committed = True
        readback = conn.execute(
            "SELECT condition_text FROM cars WHERE id=?", (card_id,)
        ).fetchone()
        if readback is None or readback[0] != text:
            raise ReadbackMismatchError("readback")
        return {"changed": changed, "text": text}
    except sqlite3.OperationalError as exc:
        if not committed:
            _rollback(conn)
        if _is_busy(exc):
            raise CrmBusyError("busy") from exc
        raise
    except Exception:
        if not committed:
            _rollback(conn)
        raise
    finally:
        conn.close()


def _read_description(db_path: str, card_id: int) -> str | None:
    conn = _connect_crm(db_path)
    try:
        try:
            _assert_live_schema(conn)
            row = conn.execute(
                "SELECT condition_text FROM cars WHERE id=?", (card_id,)
            ).fetchone()
            if row is None:
                raise CardNotFoundError("missing_card")
            return row[0]
        except sqlite3.OperationalError as exc:
            if _is_busy(exc):
                raise CrmBusyError("busy") from exc
            raise
    finally:
        conn.close()


def _open_queue(queue_path: str) -> sqlite3.Connection:
    parent = os.path.dirname(os.path.abspath(queue_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(
        queue_path,
        timeout=QUEUE_TIMEOUT_SECONDS,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=%d" % int(QUEUE_TIMEOUT_SECONDS * 1000))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(QUEUE_SCHEMA)
    try:
        os.chmod(queue_path, 0o600)
    except OSError:
        pass
    return conn


def _begin(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")


def _recover_stale(conn: sqlite3.Connection) -> None:
    cutoff = time.time() - STALE_OPERATION_SECONDS
    conn.execute(
        "UPDATE description_ops SET status='PENDING', claimed_at=NULL, "
        "error_code='recovered' WHERE status IN ('DIRECT','WORKING') "
        "AND COALESCE(claimed_at, created_at) < ?",
        (cutoff,),
    )


def _mark(
    queue_path: str,
    row_id: int,
    status: str,
    *,
    error_code: str | None = None,
    increment_attempts: bool = False,
) -> None:
    conn = _open_queue(queue_path)
    try:
        attempts = ", attempts=attempts+1" if increment_attempts else ""
        applied = ", applied_at=?" if status in ("APPLIED", "SUPERSEDED") else ""
        values: list[Any] = [status, error_code]
        if applied:
            values.append(time.time())
        values.append(row_id)
        conn.execute(
            "UPDATE description_ops SET status=?, error_code=?" + attempts + applied
            + " WHERE id=?",
            values,
        )
    finally:
        conn.close()


def _result(status: str, card_id: int, text: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "card_id": card_id,
        "field": CANONICAL_FIELD,
        "characters": len(text),
        "lines": len([line for line in text.split("\n") if line.strip()]),
    }
    result.update(extra)
    return result


def _has_older_active(conn: sqlite3.Connection, row_id: int, card_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM description_ops WHERE card_id=? AND id<? "
        "AND status IN ('DIRECT','PENDING','WORKING') LIMIT 1",
        (card_id, row_id),
    ).fetchone()
    return row is not None


def save_or_enqueue(
    db_path: str,
    queue_path: str,
    card_id: Any,
    raw_text: str,
    actor_id: Any,
    operation_id: str,
    *,
    start_worker: bool = True,
) -> dict[str, Any]:
    """Save immediately or durably enqueue within the sub-second lock budget.

    ``operation_id`` must be stable for the Telegram update (``chat_id:message_id``).
    Replaying the same update never produces a second CRM write or audit row.
    """
    text = normalize_text(raw_text)
    card = _card_id(card_id)
    actor = _actor_id(actor_id)
    op_id = _operation_id(operation_id)
    digest = _sha(text)
    conn = _open_queue(queue_path)
    row_id: int
    try:
        _begin(conn)
        _recover_stale(conn)
        existing = conn.execute(
            "SELECT * FROM description_ops WHERE operation_id=?", (op_id,)
        ).fetchone()
        if existing is not None:
            if int(existing["card_id"]) != card or existing["text_sha256"] != digest:
                conn.execute("ROLLBACK")
                raise DescriptionValidationError("operation_collision")
            status = str(existing["status"])
            conn.execute("COMMIT")
            if status == "APPLIED":
                if start_worker:
                    _start_worker(db_path, queue_path)
                return _result("saved", card, text, duplicate=True, changed=False)
            if status == "SUPERSEDED":
                return _result("superseded", card, text, duplicate=True, changed=False)
            if status == "FAILED":
                raise DescriptionError("previous_failure")
            if start_worker:
                _start_worker(db_path, queue_path)
            return _result("queued", card, text, duplicate=True, changed=False)

        now = time.time()
        cursor = conn.execute(
            "INSERT INTO description_ops "
            "(operation_id, card_id, actor_id, description_text, text_sha256, "
            "status, created_at, claimed_at) VALUES (?,?,?,?,?,'DIRECT',?,?)",
            (op_id, card, actor, text, digest, now, now),
        )
        row_id = int(cursor.lastrowid)
        older_active = _has_older_active(conn, row_id, card)
        if older_active:
            conn.execute(
                "UPDATE description_ops SET status='PENDING', claimed_at=NULL WHERE id=?",
                (row_id,),
            )
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    if older_active:
        if start_worker:
            _start_worker(db_path, queue_path)
        return _result("queued", card, text, duplicate=False, changed=False)

    try:
        written = _atomic_write(db_path, card, text, actor)
    except CrmBusyError:
        _mark(queue_path, row_id, "PENDING", error_code="busy", increment_attempts=True)
        if start_worker:
            _start_worker(db_path, queue_path)
        return _result("queued", card, text, duplicate=False, changed=False)
    except Exception:
        _mark(queue_path, row_id, "FAILED", error_code="write_failed", increment_attempts=True)
        raise
    _mark(queue_path, row_id, "APPLIED")
    if start_worker:
        _start_worker(db_path, queue_path)
    return _result(
        "saved", card, text, duplicate=False, changed=bool(written["changed"])
    )


def _acquire_lease(conn: sqlite3.Connection, owner: str) -> bool:
    now = time.time()
    _begin(conn)
    conn.execute(
        "INSERT OR IGNORE INTO description_worker_lease(name, owner, lease_until) "
        "VALUES ('global', '', 0)"
    )
    cursor = conn.execute(
        "UPDATE description_worker_lease SET owner=?, lease_until=? "
        "WHERE name='global' AND (lease_until<? OR owner=?)",
        (owner, now + WORK_LEASE_SECONDS, now, owner),
    )
    conn.execute("COMMIT")
    return cursor.rowcount == 1


def _renew_lease(conn: sqlite3.Connection, owner: str) -> None:
    conn.execute(
        "UPDATE description_worker_lease SET lease_until=? "
        "WHERE name='global' AND owner=?",
        (time.time() + WORK_LEASE_SECONDS, owner),
    )


def _release_lease(conn: sqlite3.Connection, owner: str) -> None:
    conn.execute(
        "UPDATE description_worker_lease SET lease_until=0 WHERE name='global' AND owner=?",
        (owner,),
    )


def _claim_next(conn: sqlite3.Connection) -> sqlite3.Row | None:
    _begin(conn)
    _recover_stale(conn)
    row = conn.execute(
        "SELECT * FROM description_ops WHERE status='PENDING' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        conn.execute("COMMIT")
        return None
    newer = conn.execute(
        "SELECT 1 FROM description_ops WHERE card_id=? AND id>? "
        "AND status IN ('DIRECT','PENDING','WORKING','APPLIED') LIMIT 1",
        (row["card_id"], row["id"]),
    ).fetchone()
    if newer is not None:
        conn.execute(
            "UPDATE description_ops SET status='SUPERSEDED', applied_at=?, "
            "error_code=NULL WHERE id=?",
            (time.time(), row["id"]),
        )
        conn.execute("COMMIT")
        return conn.execute(
            "SELECT * FROM description_ops WHERE id=?", (row["id"],)
        ).fetchone()
    conn.execute(
        "UPDATE description_ops SET status='WORKING', claimed_at=?, attempts=attempts+1, "
        "error_code=NULL WHERE id=? AND status='PENDING'",
        (time.time(), row["id"]),
    )
    conn.execute("COMMIT")
    return conn.execute(
        "SELECT * FROM description_ops WHERE id=?", (row["id"],)
    ).fetchone()


def drain_pending(
    db_path: str,
    queue_path: str,
    *,
    max_items: int = 100,
) -> dict[str, int]:
    """Drain queued operations under a cross-process global lease."""
    owner = "%s:%s:%s" % (os.getpid(), threading.get_ident(), uuid.uuid4().hex)
    conn = _open_queue(queue_path)
    applied = 0
    superseded = 0
    busy = 0
    try:
        if not _acquire_lease(conn, owner):
            return {"applied": 0, "superseded": 0, "busy": 0}
        for _ in range(max(0, int(max_items))):
            _renew_lease(conn, owner)
            row = _claim_next(conn)
            if row is None:
                break
            if row["status"] == "SUPERSEDED":
                superseded += 1
                continue
            row_id = int(row["id"])
            card = int(row["card_id"])
            text = str(row["description_text"])

            # A newer intent may have arrived after the claim.
            newer = conn.execute(
                "SELECT 1 FROM description_ops WHERE card_id=? AND id>? "
                "AND status IN ('DIRECT','PENDING','WORKING','APPLIED') LIMIT 1",
                (card, row_id),
            ).fetchone()
            if newer is not None:
                _mark(queue_path, row_id, "SUPERSEDED")
                superseded += 1
                continue
            try:
                if _read_description(db_path, card) != text:
                    _atomic_write(db_path, card, text, _actor_id(row["actor_id"]))
            except CrmBusyError:
                _mark(queue_path, row_id, "PENDING", error_code="busy")
                busy += 1
                break
            except Exception:
                _mark(queue_path, row_id, "FAILED", error_code="write_failed")
                continue
            _mark(queue_path, row_id, "APPLIED")
            applied += 1
        return {"applied": applied, "superseded": superseded, "busy": busy}
    finally:
        try:
            _release_lease(conn, owner)
        finally:
            conn.close()


def _worker_main(db_path: str, queue_path: str, key: str) -> None:
    try:
        deadline = time.monotonic() + 90.0
        delay = 0.35
        while time.monotonic() < deadline:
            result = drain_pending(db_path, queue_path, max_items=100)
            conn = _open_queue(queue_path)
            try:
                pending = conn.execute(
                    "SELECT COUNT(*) FROM description_ops WHERE status IN ('PENDING','WORKING','DIRECT')"
                ).fetchone()[0]
            finally:
                conn.close()
            if not pending:
                return
            if not result["busy"] and not result["applied"] and not result["superseded"]:
                delay = min(delay * 1.7, 3.0)
            time.sleep(delay)
    finally:
        with _THREAD_GUARD:
            _WORKERS.discard(key)


def _start_worker(db_path: str, queue_path: str) -> None:
    key = os.path.abspath(db_path) + "|" + os.path.abspath(queue_path)
    with _THREAD_GUARD:
        if key in _WORKERS:
            return
        _WORKERS.add(key)
    thread = threading.Thread(
        target=_worker_main,
        args=(db_path, queue_path, key),
        name="crm-description-writer",
        daemon=True,
    )
    thread.start()


def start_worker(db_path: str, queue_path: str) -> None:
    """Public restart hook; safe to call repeatedly."""
    _start_worker(db_path, queue_path)


def safe_user_message(exc: BaseException) -> str:
    """Return a short Telegram-safe error without paths or lock details."""
    if isinstance(exc, DescriptionValidationError):
        code = str(exc)
        if code == "too_long":
            return "Описание слишком длинное: максимум 12 000 знаков."
        if code == "empty":
            return "Пустое описание не сохраняю."
        return "Не удалось проверить описание. Режим ввода сохранён."
    if isinstance(exc, CardNotFoundError):
        return "Карточка не найдена. Откройте её заново; новая карточка не создана."
    return "Не удалось сохранить описание. Режим ввода сохранён — повторите позже."
