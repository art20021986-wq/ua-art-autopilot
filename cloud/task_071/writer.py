"""TASK 071 — the single real writer for `cars` and allowlisted `clients` fields.

Hard allowlist built from the confirmed real schema in
cloud/task_070/evidence/real_context.json. Table and field names are NEVER
taken from free-form input; only keys present in ALLOWED_TABLES are ever used
to build SQL, and only as identifiers already present in this Python source
(never interpolated from caller-controlled strings).
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional

# Real schema allowlist (see cloud/task_070/evidence/real_context.json).
ALLOWED_TABLES: dict[str, dict[str, str]] = {
    "cars": {
        "price_uah": "numeric",
        "mileage_km": "numeric",
        "status": "text",
        "stage": "text",  # legacy alias, mapped to status
        "sea_container": "text",
        "days_to_kyiv": "numeric",
        "eta_manual": "text",
    },
    "clients": {
        "name": "text",
        "phone": "text",
        "note": "text",
    },
}

FIELD_ALIASES = {"stage": "status"}

# Fixed, literal SQL column names per (table, resolved field) — never built
# from caller input, only selected from this static mapping.
_UPDATE_SQL = {
    ("cars", "price_uah"): "UPDATE cars SET price_uah=?, price_history=? WHERE id=?",
    ("cars", "mileage_km"): "UPDATE cars SET mileage_km=? WHERE id=?",
    ("cars", "status"): "UPDATE cars SET status=? WHERE id=?",
    ("cars", "sea_container"): "UPDATE cars SET sea_container=? WHERE id=?",
    ("cars", "days_to_kyiv"): "UPDATE cars SET days_to_kyiv=? WHERE id=?",
    ("cars", "eta_manual"): "UPDATE cars SET eta_manual=? WHERE id=?",
    ("clients", "name"): "UPDATE clients SET name=? WHERE id=?",
    ("clients", "phone"): "UPDATE clients SET phone=? WHERE id=?",
    ("clients", "note"): "UPDATE clients SET note=? WHERE id=?",
}


class RejectedField(Exception):
    pass


def resolve_field(table: str, field: str) -> str:
    if table not in ALLOWED_TABLES:
        raise RejectedField(f"table not allowed: {table!r}")
    real_field = FIELD_ALIASES.get(field, field)
    if real_field not in ALLOWED_TABLES[table]:
        raise RejectedField(f"field not allowed for table {table!r}: {field!r}")
    return real_field


def apply_field_update(
    conn: sqlite3.Connection,
    table: str,
    card_id: int,
    field: str,
    value: Any,
    operation_id: str,
    actor: str = "cars_ui",
    direct_write_budget_s: float = 0.8,
) -> dict:
    """Apply exactly one CRM field change: one UPDATE + one audit INSERT in a
    single transaction / single commit / single connection. For price_uah the
    price_history JSON is embedded in the same UPDATE so no second commit or
    separate remember_price call is required.

    Idempotent by operation_id: if this operation_id already produced an audit
    row, the call is a no-op and returns {'status': 'duplicate_ignored'}.
    """
    real_field = resolve_field(table, field)
    started = time.monotonic()

    cur = conn.cursor()
    cur.execute("SELECT 1 FROM audit WHERE operation_id=?", (operation_id,))
    if cur.fetchone():
        return {"status": "duplicate_ignored", "operation_id": operation_id}

    try:
        with conn:  # single transaction, single commit
            if table == "cars" and real_field == "price_uah":
                cur.execute("SELECT price_history FROM cars WHERE id=?", (card_id,))
                row = cur.fetchone()
                history = json.loads(row[0]) if row and row[0] else []
                history.append({
                    "price_uah": value,
                    "ts": time.time(),
                    "operation_id": operation_id,
                })
                cur.execute(
                    _UPDATE_SQL[("cars", "price_uah")],
                    (value, json.dumps(history), card_id),
                )
            else:
                sql = _UPDATE_SQL[(table, real_field)]
                cur.execute(sql, (value, card_id))

            cur.execute(
                "INSERT INTO audit(card_id, table_name, field, value, operation_id, actor, ts) "
                "VALUES (?,?,?,?,?,?,?)",
                (card_id, table, real_field, str(value), operation_id, actor, time.time()),
            )
    except sqlite3.OperationalError as exc:
        elapsed = time.monotonic() - started
        if elapsed <= direct_write_budget_s and ("locked" in str(exc) or "busy" in str(exc)):
            raise
        raise

    return {"status": "ok", "operation_id": operation_id, "table": table, "field": real_field}


def read_back(conn: sqlite3.Connection, table: str, field: str, card_id: int) -> Optional[Any]:
    real_field = resolve_field(table, field)
    cur = conn.cursor()
    cur.execute(f"SELECT {real_field} FROM {table} WHERE id=?", (card_id,))
    row = cur.fetchone()
    return row[0] if row else None
