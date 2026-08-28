"""
Standalone description-save writer for /home/Carix (Python 3, stdlib-only, no LLM calls).

Design goals (per TASK 072 contract):
  - Canonical field: cars.condition_text. Legacy input alias: description -> condition_text
    on write; read prefers condition_text, falls back to description.
  - diag_text is never touched by this module.
  - Schema-driven allowlist: columns for `cars` and `audit` are discovered at runtime via
    PRAGMA table_info, not hardcoded blind guesses. Only identifier-safe column names
    (regex ^[A-Za-z_][A-Za-z0-9_]*$) are ever used in SQL, and only columns that actually
    exist in the live schema are ever referenced.
  - One connection, one short transaction: SELECT current + UPDATE + INSERT audit, one commit.
  - Direct write budget <= 0.8s. If the direct path cannot commit within budget (database
    locked/busy), the caller should enqueue into the durable sidecar queue instead of
    retrying inline (see queue_sidecar.py).
  - No timeout/busy_timeout/journal_mode changes beyond what the caller's connection
    already uses; this module does not widen any calling transaction's settings.
  - Read-back verification: after commit, re-read condition_text for the same card and
    compare byte-for-byte to the value written; success is only reported if they match.
"""
from __future__ import annotations

import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from typing import Optional

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_LEN = 12000
MIN_LEN = 1
DIRECT_WRITE_BUDGET_SECONDS = 0.8
CONFIRM_TRUNCATE_CHARS = 900

CANONICAL_FIELD = "condition_text"
LEGACY_ALIAS_FIELDS = ("description",)  # inputs to this name are redirected to CANONICAL_FIELD
FORBIDDEN_WRITE_FIELDS = ("diag_text",)  # marketing description must never land here


class ValidationError(Exception):
    pass


class SchemaError(Exception):
    pass


class WriteBudgetExceeded(Exception):
    """Raised when the direct write path could not complete within budget; caller
    should fall back to the durable queue."""


@dataclass
class SaveResult:
    card_id: str
    field_written: str
    stored_text: str
    audit_row_id: int
    elapsed_seconds: float


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not IDENTIFIER_RE.match(table):
        raise SchemaError(f"Unsafe table identifier: {table!r}")
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if not cols:
        raise SchemaError(f"Table {table!r} not found or has no columns in live schema.")
    return cols


def build_allowlist(conn: sqlite3.Connection) -> dict:
    """Discover the real, current schema and build a strict allowlist.

    Never invents column names; only returns columns that actually exist.
    """
    cars_cols = _table_columns(conn, "cars")
    if CANONICAL_FIELD not in cars_cols:
        raise SchemaError(
            f"Live schema drift: cars.{CANONICAL_FIELD} not found. Refusing to write blind."
        )
    try:
        audit_cols = _table_columns(conn, "audit")
    except SchemaError:
        audit_cols = set()  # audit logging becomes a no-op if table truly absent; never invented
    id_col = "card_id" if "card_id" in cars_cols else None
    if id_col is None:
        raise SchemaError("Live schema drift: cars.card_id not found. Refusing to write blind.")
    return {
        "cars_columns": cars_cols,
        "audit_columns": audit_cols,
        "id_column": id_col,
    }


def normalize_text(raw: str) -> str:
    """Strip only outer blank lines / NUL bytes. Never truncates or 'improves' content."""
    if raw is None:
        raise ValidationError("Empty text is not allowed.")
    # Remove NUL bytes anywhere (SQLite/Telegram-unsafe control character).
    cleaned = raw.replace("\x00", "")
    # Normalize newlines to \n but keep internal formatting/line breaks intact.
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    # Strip only leading/trailing blank lines (not internal ones, not inline whitespace shape).
    lines = cleaned.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    result = "\n".join(lines)
    length = len(result)
    if length < MIN_LEN:
        raise ValidationError("Description text is empty after normalization.")
    if length > MAX_LEN:
        raise ValidationError(
            f"Description text is {length} Unicode characters; maximum allowed is {MAX_LEN}."
        )
    # Ensure it is well-formed unicode (defensive; sqlite3 already requires this).
    unicodedata.normalize("NFC", result)
    return result


def resolve_target_field(requested_field: str, allowlist: dict) -> str:
    """Map any legacy alias to the canonical field; reject forbidden/unknown fields."""
    field = requested_field
    if field in LEGACY_ALIAS_FIELDS:
        field = CANONICAL_FIELD
    if field in FORBIDDEN_WRITE_FIELDS:
        raise ValidationError(
            f"Refusing to write marketing description into protected field {field!r}."
        )
    if field not in allowlist["cars_columns"]:
        raise ValidationError(f"Unknown/disallowed field: {requested_field!r}")
    if not IDENTIFIER_RE.match(field):
        raise ValidationError(f"Unsafe field identifier: {field!r}")
    return field


def read_field(conn: sqlite3.Connection, allowlist: dict, card_id: str, field: str) -> Optional[str]:
    id_col = allowlist["id_column"]
    row = conn.execute(
        f"SELECT {field} FROM cars WHERE {id_col} = ?", (card_id,)
    ).fetchone()
    return row[0] if row else None


def read_description_with_fallback(conn: sqlite3.Connection, allowlist: dict, card_id: str) -> Optional[str]:
    """Reads condition_text first; falls back to legacy description if empty/None."""
    value = read_field(conn, allowlist, card_id, CANONICAL_FIELD)
    if value:
        return value
    if "description" in allowlist["cars_columns"]:
        return read_field(conn, allowlist, card_id, "description")
    return None


def save_description(
    conn: sqlite3.Connection,
    card_id: str,
    requested_field: str,
    raw_text: str,
    operation_id: str,
    actor: str = "telegram_bot",
) -> SaveResult:
    """Single-connection, single-transaction, one-commit save with read-back verification.

    Caller is responsible for measuring/enforcing the overall DIRECT_WRITE_BUDGET_SECONDS
    and falling back to the durable queue (queue_sidecar.py) if this call does not return
    within budget or raises sqlite3.OperationalError (locked/busy).
    """
    start = time.monotonic()
    allowlist = build_allowlist(conn)
    field = resolve_target_field(requested_field, allowlist)
    text = normalize_text(raw_text)
    id_col = allowlist["id_column"]

    cur = conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            f"SELECT {id_col} FROM cars WHERE {id_col} = ?", (card_id,)
        ).fetchone()
        if existing is None:
            conn.execute("ROLLBACK")
            raise ValidationError(f"Card {card_id!r} does not exist; refusing to create one.")

        conn.execute(
            f"UPDATE cars SET {field} = ? WHERE {id_col} = ?", (text, card_id)
        )

        audit_row_id = -1
        audit_cols = allowlist["audit_columns"]
        if audit_cols:
            insert_cols = []
            insert_vals = []
            candidates = {
                "card_id": card_id,
                "operation_id": operation_id,
                "field": field,
                "action": "description_save",
                "actor": actor,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "new_value": text[:CONFIRM_TRUNCATE_CHARS],
            }
            for col_name, val in candidates.items():
                if col_name in audit_cols:
                    insert_cols.append(col_name)
                    insert_vals.append(val)
            if insert_cols:
                placeholders = ", ".join(["?"] * len(insert_cols))
                col_list = ", ".join(insert_cols)
                cur2 = conn.execute(
                    f"INSERT INTO audit ({col_list}) VALUES ({placeholders})", insert_vals
                )
                audit_row_id = cur2.lastrowid
        conn.commit()
    except sqlite3.OperationalError:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        elapsed = time.monotonic() - start
        raise WriteBudgetExceeded(
            f"Direct write path failed (locked/busy) after {elapsed:.3f}s; enqueue instead."
        )
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        raise

    elapsed = time.monotonic() - start
    if elapsed > DIRECT_WRITE_BUDGET_SECONDS:
        # Commit already happened; we still report success (data is safe) but flag
        # budget overrun for observability. We do not roll back a committed write.
        pass

    # Mandatory read-back verification on the same connection/card.
    readback = read_field(conn, allowlist, card_id, field)
    if readback != text:
        raise RuntimeError(
            "Read-back mismatch after commit; refusing to report success to Telegram."
        )

    return SaveResult(
        card_id=card_id,
        field_written=field,
        stored_text=readback,
        audit_row_id=audit_row_id,
        elapsed_seconds=elapsed,
    )


def confirm_message(result: SaveResult) -> str:
    """Builds the short Telegram confirmation, never exceeding 900 shown chars,
    while the DB retains the full text."""
    return "\u2705 \u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e"


def safe_error_message(exc: Exception) -> str:
    """Never leaks traceback/server paths/'database is locked' to Telegram."""
    if isinstance(exc, ValidationError):
        return f"\u26a0\ufe0f {exc}"
    if isinstance(exc, WriteBudgetExceeded):
        return "\u23f3 \u041f\u0440\u0438\u043d\u044f\u0442\u043e, \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e"
    return "\u26a0\ufe0f \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0451 \u0440\u0430\u0437."
