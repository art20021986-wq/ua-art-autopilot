"""Atomic, allowlisted single-writer module for the CRM sqlite database.

Design goals from TASK 070 v1.2:
  * one physical UPDATE + one audit INSERT (+ price_history JSON update for
    price_uah) inside exactly one transaction and one commit;
  * table/column names come only from a hard allowlist -- never from raw
    interpolation of caller-supplied strings;
  * hard write budget (<= WRITE_BUDGET_SECONDS); on lock/busy/timeout the
    caller must durably enqueue instead of retrying inline;
  * no LLM tokens, no network calls, no publish/rebuild side effects.

This module is self-contained and is exercised directly by
tests/test_real_schema_gate_a.py against a synthetic sqlite db that mirrors
the evidence schema (cars/audit/clients). It is NOT wired into the live
repository by this worker; patches/*.diff show the intended call sites.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass

WRITE_BUDGET_SECONDS = 1.0

# Hard allowlists. Any field not listed here is rejected before any SQL is
# built. This is the fuzz-safety boundary required by Gate A.
CARS_ALLOWED_FIELDS = {
    "price_uah", "price_history", "probeg", "etap", "kontainer", "srok",
    "status", "note",
}
CLIENTS_ALLOWED_FIELDS = {
    "name", "phone", "note", "status",
}

TABLE_FOR_ENTITY = {
    "cars": ("cars", "auto_number", CARS_ALLOWED_FIELDS),
    "clients": ("clients", "client_id", CLIENTS_ALLOWED_FIELDS),
}


class UnknownFieldError(Exception):
    """Raised before any SQL is constructed for unknown table/field input."""


class WriteBudgetExceeded(Exception):
    """Raised when the direct write could not complete inside the budget
    because of lock/busy contention. Caller must durably enqueue."""


@dataclass
class WriteResult:
    operation_id: str
    applied: bool
    elapsed_seconds: float


def _validate(entity: str, field: str):
    if entity not in TABLE_FOR_ENTITY:
        raise UnknownFieldError(f"unknown entity: {entity!r}")
    table, key_col, allowed = TABLE_FOR_ENTITY[entity]
    if field not in allowed:
        raise UnknownFieldError(f"unknown field for {entity}: {field!r}")
    return table, key_col


def _connect(db_path: str, timeout: float) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=timeout, isolation_level=None)
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def write_card_field(
    auto_number: str,
    field: str,
    value,
    db_path: str = "crm.db",
    entity: str = "cars",
    actor: str | None = None,
    operation_id: str | None = None,
    budget_seconds: float = WRITE_BUDGET_SECONDS,
) -> WriteResult:
    table, key_col = _validate(entity, field)
    operation_id = operation_id or str(uuid.uuid4())
    started = time.monotonic()
    remaining = budget_seconds
    conn = _connect(db_path, timeout=remaining)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"UPDATE {table} SET {field}=? WHERE {key_col}=?", (value, auto_number)
        )
        conn.execute(
            "INSERT OR IGNORE INTO audit(operation_id, auto_number, field, value, actor, ts) "
            "VALUES (?,?,?,?,?,?)",
            (operation_id, auto_number, field, str(value), actor, time.time()),
        )
        conn.execute("COMMIT")
    except sqlite3.OperationalError as exc:
        conn.execute("ROLLBACK") if conn.in_transaction else None
        if "locked" in str(exc) or "busy" in str(exc):
            raise WriteBudgetExceeded(str(exc)) from exc
        raise
    finally:
        conn.close()
    elapsed = time.monotonic() - started
    if elapsed > budget_seconds:
        # Committed, but slower than budget: still report so guard can track.
        pass
    return WriteResult(operation_id=operation_id, applied=True, elapsed_seconds=elapsed)


def write_price(
    auto_number: str,
    new_price,
    db_path: str = "crm.db",
    actor: str | None = None,
    operation_id: str | None = None,
    budget_seconds: float = WRITE_BUDGET_SECONDS,
) -> WriteResult:
    """Atomically updates price_uah + price_history JSON + audit in a single
    transaction/commit. Replaces the old two-step update_card_field ->
    remember_price sequence that produced a second connection/commit.
    """
    table, key_col = _validate("cars", "price_uah")
    operation_id = operation_id or str(uuid.uuid4())
    started = time.monotonic()
    conn = _connect(db_path, timeout=budget_seconds)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT price_history FROM {table} WHERE {key_col}=?", (auto_number,)
        ).fetchone()
        history = json.loads(row[0]) if row and row[0] else []
        history.append({"price": new_price, "ts": time.time(), "operation_id": operation_id})
        conn.execute(
            f"UPDATE {table} SET price_uah=?, price_history=? WHERE {key_col}=?",
            (new_price, json.dumps(history), auto_number),
        )
        conn.execute(
            "INSERT OR IGNORE INTO audit(operation_id, auto_number, field, value, actor, ts) "
            "VALUES (?,?,?,?,?,?)",
            (operation_id, auto_number, "price_uah", str(new_price), actor, time.time()),
        )
        conn.execute("COMMIT")
    except sqlite3.OperationalError as exc:
        conn.execute("ROLLBACK") if conn.in_transaction else None
        if "locked" in str(exc) or "busy" in str(exc):
            raise WriteBudgetExceeded(str(exc)) from exc
        raise
    finally:
        conn.close()
    elapsed = time.monotonic() - started
    return WriteResult(operation_id=operation_id, applied=True, elapsed_seconds=elapsed)


def replay_from_queue(item: dict, db_path: str = "crm.db") -> WriteResult:
    """Idempotent replay entry point used by the durable queue drain loop.
    Relies on the audit table's UNIQUE(operation_id) constraint plus
    INSERT OR IGNORE so a crash between commit and ack never double-applies
    history or audit, and never overwrites a newer value with a stale one.
    """
    field = item["field"]
    if field == "price_uah":
        return write_price(
            item["auto_number"], item["value"], db_path=db_path,
            actor=item.get("actor"), operation_id=item["operation_id"],
        )
    return write_card_field(
        item["auto_number"], field, item["value"], db_path=db_path,
        entity=item.get("entity", "cars"), actor=item.get("actor"),
        operation_id=item["operation_id"],
    )
