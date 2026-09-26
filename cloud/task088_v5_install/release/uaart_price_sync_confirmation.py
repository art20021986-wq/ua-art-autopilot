"""Durable, immutable operator price confirmations; no network or auto-install.

The caller owns one BEGIN IMMEDIATE transaction and rechecks the existing CRM
ACL before each proposal, confirmation, cancellation and accepted operation.
The bounds flag an input for review; they never modify or reject an amount.
"""
import hashlib
import json
import re
import sqlite3

TABLE = "uaart_price_confirmation_v5"
REVIEW_BELOW_USD = 1000
REVIEW_ABOVE_USD = 200000
_DDL = f"""CREATE TABLE {TABLE} (
 token TEXT PRIMARY KEY NOT NULL,
 event_key TEXT UNIQUE NOT NULL,
 payload_json TEXT NOT NULL,
 created_ms INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('PENDING','CONFIRMED','CANCELLED')),
 decided_ms INTEGER
)"""


class ConfirmationError(RuntimeError):
    pass


class PriceReply(str):
    def __new__(cls, text, *, confirmation=None, queued=False):
        result = super().__new__(cls, text)
        result.confirmation = confirmation
        result.queued = queued
        return result


def _transaction(conn):
    if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
        raise ConfirmationError("CALLER_TRANSACTION_REQUIRED")


def install(conn):
    """Explicit installation only; never touch the Stage 1/2 cars schema."""
    _transaction(conn)
    existing = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                            (TABLE,)).fetchone()
    if existing is None:
        conn.execute(_DDL)
    elif existing[0] != _DDL:
        raise ConfirmationError("CONFIRMATION_SCHEMA_MISMATCH")
    triggers = {
        TABLE + "_no_delete": f"CREATE TRIGGER {TABLE}_no_delete BEFORE DELETE ON {TABLE} "
        "BEGIN SELECT RAISE(ABORT,'PRICE_CONFIRMATION_PERMANENT'); END",
        TABLE + "_immutable": f"CREATE TRIGGER {TABLE}_immutable BEFORE UPDATE ON {TABLE} "
        "WHEN NEW.token IS NOT OLD.token OR NEW.event_key IS NOT OLD.event_key "
        "OR NEW.payload_json IS NOT OLD.payload_json OR NEW.created_ms IS NOT OLD.created_ms "
        "OR OLD.state != 'PENDING' OR NEW.state NOT IN ('CONFIRMED','CANCELLED') "
        "OR NEW.decided_ms IS NULL "
        "BEGIN SELECT RAISE(ABORT,'PRICE_CONFIRMATION_IMMUTABLE'); END",
    }
    for name, ddl in triggers.items():
        existing = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                                (name,)).fetchone()
        if existing is None:
            conn.execute(ddl)
        elif existing[0] != ddl:
            raise ConfirmationError("CONFIRMATION_TRIGGER_MISMATCH")


def suspicious(value):
    return value is not None and (value < REVIEW_BELOW_USD or value > REVIEW_ABOVE_USD)


def get(conn, token):
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ConfirmationError("INVALID_CONFIRMATION_TOKEN")
    cursor = conn.execute(f"SELECT * FROM {TABLE} WHERE token=?", (token,))
    row = cursor.fetchone()
    if row is None:
        return None
    result = dict(zip((col[0] for col in cursor.description), row))
    result["payload"] = json.loads(result["payload_json"])
    return result


def get_for_event(conn, event_key):
    if not isinstance(event_key, str) or not re.fullmatch(r"[0-9a-f]{64}", event_key):
        raise ConfirmationError("INVALID_OPERATION_KEY")
    row = conn.execute(f"SELECT token FROM {TABLE} WHERE event_key=?", (event_key,)).fetchone()
    return get(conn, row[0]) if row is not None else None


def propose(conn, *, event_key, payload, now_ms):
    _transaction(conn)
    if not isinstance(event_key, str) or not re.fullmatch(r"[0-9a-f]{64}", event_key):
        raise ConfirmationError("INVALID_OPERATION_KEY")
    token = hashlib.sha256(("PRICE_CONFIRM_V5:" + event_key).encode()).hexdigest()[:32]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    before = get(conn, token)
    if before is not None:
        if before["event_key"] != event_key or before["payload_json"] != encoded:
            raise ConfirmationError("CONFIRMATION_IDENTITY_CONFLICT")
        return before
    conn.execute(f"INSERT INTO {TABLE}(token,event_key,payload_json,created_ms,state) "
                 "VALUES(?,?,?,?,'PENDING')", (token, event_key, encoded, now_ms))
    saved = get(conn, token)
    if (saved is None or saved["payload_json"] != encoded or saved["state"] != "PENDING"
            or saved["event_key"] != event_key):
        raise ConfirmationError("CONFIRMATION_INSERT_MISMATCH")
    return saved


def check_identity(proposal, *, actor_id, chat_id, car_id=None):
    if proposal is None:
        raise ConfirmationError("CONFIRMATION_NOT_FOUND")
    payload = proposal["payload"]
    if (payload["actor_id"] != actor_id or payload["chat_id"] != chat_id
            or (car_id is not None and payload["car_id"] != car_id)):
        raise ConfirmationError("CONFIRMATION_IDENTITY_MISMATCH")
    return payload


def decide(conn, token, *, state, now_ms):
    _transaction(conn)
    if state not in ("CONFIRMED", "CANCELLED"):
        raise ConfirmationError("INVALID_CONFIRMATION_DECISION")
    row = get(conn, token)
    if row is None:
        raise ConfirmationError("CONFIRMATION_NOT_FOUND")
    if row["state"] == state:
        return row
    if row["state"] != "PENDING":
        raise ConfirmationError("CONFIRMATION_ALREADY_DECIDED")
    conn.execute(f"UPDATE {TABLE} SET state=?,decided_ms=? WHERE token=? AND state='PENDING'",
                 (state, now_ms, token))
    saved = get(conn, token)
    if saved["state"] != state or saved["payload_json"] != row["payload_json"]:
        raise ConfirmationError("CONFIRMATION_DECISION_MISMATCH")
    return saved
