"""Uninstalled legacy SQLite deletion candidate; no import-time side effects.

The integrator owns the connection, staff authorization, publication fence,
exact surface discovery, backup, and retirement verifier. Every mutation is
made through a caller-controlled BEGIN IMMEDIATE session. No cars migration,
HTTP request, filesystem removal, bot message, or V5 runtime is implemented.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import secrets
import sqlite3


class DeletionError(RuntimeError):
    pass


SCHEMA = {
    "ua_delete_confirmations": """CREATE TABLE ua_delete_confirmations (
        token TEXT PRIMARY KEY, actor_id INTEGER NOT NULL,
        car_id INTEGER NOT NULL, car_code TEXT NOT NULL, vin TEXT NOT NULL,
        snapshot TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL,
        operation_id TEXT
    )""",
    "ua_delete_intents": """CREATE TABLE ua_delete_intents (
        operation_id TEXT PRIMARY KEY, car_id INTEGER NOT NULL UNIQUE,
        car_code TEXT NOT NULL UNIQUE, vin TEXT NOT NULL,
        actor_id INTEGER NOT NULL, snapshot TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL, expected_snapshot TEXT NOT NULL,
        expected_snapshot_sha256 TEXT NOT NULL, plan TEXT NOT NULL,
        plan_sha256 TEXT NOT NULL, backup_sha256 TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('REQUESTED','ROW_DELETED','COMPLETE')),
        proof TEXT, proof_sha256 TEXT
    )""",
    "ua_delete_jobs": """CREATE TABLE ua_delete_jobs (
        operation_id TEXT PRIMARY KEY,
        state TEXT NOT NULL CHECK(state IN ('PENDING','ROW_DELETED','COMPLETE')),
        FOREIGN KEY(operation_id) REFERENCES ua_delete_intents(operation_id)
            ON DELETE RESTRICT
    )""",
}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise DeletionError("SHA256_REQUIRED")
    return value


def _code(value):
    if not isinstance(value, str) or re.fullmatch(r"UA-[0-9]{4}", value) is None:
        raise DeletionError("EXACT_CAR_CODE_REQUIRED")
    return value


def canonical_vin(value):
    return re.sub(r"[\s-]+", "", str(value or "")).upper()


def _positive_int(value):
    if type(value) is not int or value <= 0:
        raise DeletionError("POSITIVE_INTEGER_REQUIRED")
    return value


def _row(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    value = cursor.fetchone()
    return None if value is None else dict(zip((d[0] for d in cursor.description), value))


def _snapshot(row):
    # SQLite types are encoded explicitly: blobs, integer/real distinction,
    # NULL, and exact floating point values survive the preimage unchanged.
    def cell(value):
        if value is None:
            return ["null", None]
        if type(value) is int:
            return ["integer", str(value)]
        if type(value) is float and math.isfinite(value):
            return ["real", value.hex()]
        if type(value) is str:
            return ["text", value]
        if type(value) is bytes:
            return ["blob", base64.b64encode(value).decode("ascii")]
        raise DeletionError("UNSUPPORTED_SQLITE_VALUE")
    return _json({key: cell(value) for key, value in row.items()})


def application_schema_sha256(conn):
    """Inspection only; a human/release review must approve this exact digest."""
    items = [list(row) for row in conn.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name")
        if row[1] not in SCHEMA]
    return _sha(_json(items))


class ImmediateTransaction:
    """Caller begins, commits/rolls back; an exception always rolls back.

    Do not use conn.commit()/rollback() behind this object. Holding the same
    fence throughout this session is required, including the final commit.
    The context manager rolls back unless the caller explicitly commits.
    """
    def __init__(self, conn, require_fence):
        if not callable(require_fence):
            raise DeletionError("FENCE_ASSERTION_REQUIRED")
        self.conn, self.require_fence = conn, require_fence
        self.active = False
        require_fence()
        if conn.in_transaction:
            raise DeletionError("CLEAN_CONNECTION_REQUIRED")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise DeletionError("FOREIGN_KEYS_MUST_BE_ENABLED_BEFORE_BEGIN")
        conn.execute("BEGIN IMMEDIATE")
        self.active = True

    def check(self):
        self.require_fence()
        if not self.active or not self.conn.in_transaction:
            raise DeletionError("LIVE_IMMEDIATE_TRANSACTION_REQUIRED")

    def commit(self):
        self.check()
        self.conn.commit()
        self.active = False

    def rollback(self):
        if self.active:
            self.conn.rollback()
            self.active = False

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, kind, value, traceback):
        self.rollback()
        return False


def install_additive_schema(tx, *, approved_application_schema_sha256):
    """Explicit only, after backup and live-schema review; never auto-migrate."""
    tx.check()
    if application_schema_sha256(tx.conn) != _hash(approved_application_schema_sha256):
        raise DeletionError("APPLICATION_SCHEMA_NOT_APPROVED")
    for name, ddl in SCHEMA.items():
        current = tx.conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
        if current is None:
            tx.conn.execute(ddl)
        elif current[0] != ddl:
            raise DeletionError("DELETION_SCHEMA_COLLISION:" + name)


class DeletionStore:
    def __init__(self, *, approved_application_schema_sha256, verify_retirement):
        self.schema_sha = _hash(approved_application_schema_sha256)
        if not callable(verify_retirement):
            raise DeletionError("TRUSTED_RETIREMENT_VERIFIER_REQUIRED")
        self.verify_retirement = verify_retirement

    def _check(self, tx):
        tx.check()
        if application_schema_sha256(tx.conn) != self.schema_sha:
            raise DeletionError("APPLICATION_SCHEMA_CHANGED")
        for name, ddl in SCHEMA.items():
            current = tx.conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
            if not current or current[0] != ddl:
                raise DeletionError("EXACT_DELETION_SCHEMA_REQUIRED")

    def require_writable(self, tx, *, car_id, car_code, vin):
        """All delayed writers and admission of reused identities must call this."""
        self._check(tx)
        blocked = tx.conn.execute(
            "SELECT operation_id FROM ua_delete_intents WHERE car_id=? OR car_code=? "
            "OR (vin<>'' AND vin=?)",
            (_positive_int(car_id), _code(car_code), canonical_vin(vin))).fetchone()
        if blocked:
            raise DeletionError("DELETION_IDENTITY_RESERVED:" + blocked[0])

    def confirm(self, tx, *, car_id, actor_id):
        """Bind the confirmation button to full current row, not numeric ID alone."""
        self._check(tx)
        _positive_int(actor_id)
        row = _row(tx.conn, "SELECT * FROM cars WHERE id=?", (_positive_int(car_id),))
        if row is None:
            raise DeletionError("CAR_MISSING_NO_NEW_INTENT_ALLOWED")
        code, vin = _code(row.get("auto_number")), canonical_vin(row.get("vin"))
        if tx.conn.execute("SELECT count(*) FROM cars WHERE id=? OR auto_number=?", (car_id, code)).fetchone()[0] != 1:
            raise DeletionError("AMBIGUOUS_CURRENT_CAR_CODE")
        self.require_writable(tx, car_id=car_id, car_code=code, vin=vin)
        snapshot = _snapshot(row)
        token = secrets.token_hex(16)
        tx.conn.execute("INSERT INTO ua_delete_confirmations VALUES (?,?,?,?,?,?,?,NULL)",
                        (token, actor_id, car_id, code, vin, snapshot, _sha(snapshot)))
        return token

    def _job(self, tx, operation_id):
        intent = _row(tx.conn, "SELECT * FROM ua_delete_intents WHERE operation_id=?", (operation_id,))
        job = _row(tx.conn, "SELECT * FROM ua_delete_jobs WHERE operation_id=?", (operation_id,))
        if intent is None or job is None:
            raise DeletionError("ORIGINAL_DURABLE_INTENT_AND_JOB_REQUIRED")
        expected = {"REQUESTED": "PENDING", "ROW_DELETED": "ROW_DELETED", "COMPLETE": "COMPLETE"}
        if job["state"] != expected.get(intent["state"]):
            raise DeletionError("INTENT_JOB_STATE_MISMATCH")
        for field in ("snapshot", "expected_snapshot", "plan"):
            if _sha(intent[field]) != intent[field + "_sha256"]:
                raise DeletionError("INTENT_INTEGRITY_FAILED")
        if intent["proof"] is not None and _sha(intent["proof"]) != intent["proof_sha256"]:
            raise DeletionError("PROOF_INTEGRITY_FAILED")
        return intent

    @staticmethod
    def _plan(plan, row):
        if not isinstance(plan, dict) or set(plan) != {
            "mode", "car_code", "public_targets", "list_surfaces", "media_targets"
        }:
            raise DeletionError("EXACT_RETIREMENT_PLAN_REQUIRED")
        if plan["car_code"] != row["auto_number"]:
            raise DeletionError("PLAN_IDENTITY_MISMATCH")
        for field in ("public_targets", "list_surfaces", "media_targets"):
            values = plan[field]
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                raise DeletionError("EXACT_TARGET_LIST_REQUIRED")
            if values != sorted(set(values)):
                raise DeletionError("UNIQUE_SORTED_TARGETS_REQUIRED")
        # Publication flag false alone never establishes NEVER_PUBLISHED.
        if row.get("published") not in (0, 1):
            raise DeletionError("REVIEW_PUBLICATION_FLAG_REQUIRED")
        if plan["mode"] == "NEVER_PUBLISHED":
            if row["published"] != 0 or plan["public_targets"] or not plan["list_surfaces"]:
                raise DeletionError("NEVER_PUBLISHED_PLAN_CONFLICT")
        elif plan["mode"] == "PUBLIC_OR_RESIDUAL":
            if not plan["public_targets"] or not plan["list_surfaces"]:
                raise DeletionError("EXACT_PUBLIC_SURFACES_REQUIRED")
        else:
            raise DeletionError("UNKNOWN_RETIREMENT_MODE")
        return _json(plan)

    def admit(self, tx, *, token, actor_id, plan, backup_sha256):
        """Atomically admit intent+job and set published=0; retain original row."""
        self._check(tx)
        confirmation = _row(tx.conn, "SELECT * FROM ua_delete_confirmations WHERE token=?", (token,))
        if confirmation is None or confirmation["actor_id"] != _positive_int(actor_id):
            raise DeletionError("AUTHORIZED_CONFIRMATION_REQUIRED")
        if _sha(confirmation["snapshot"]) != confirmation["snapshot_sha256"]:
            raise DeletionError("CONFIRMATION_INTEGRITY_FAILED")
        if confirmation["operation_id"]:
            # Idempotent callback resumes only its original durable operation.
            # A caller's replacement plan/backup is intentionally ignored.
            intent = self._job(tx, confirmation["operation_id"])
            self._assert_no_replacement(tx, intent)
            return intent
        existing = _row(tx.conn, "SELECT * FROM ua_delete_intents WHERE car_id=? OR car_code=?",
                        (confirmation["car_id"], confirmation["car_code"]))
        if existing:
            if existing["snapshot"] != confirmation["snapshot"]:
                raise DeletionError("DELETED_IDENTITY_REUSE_REFUSED")
            intent = self._job(tx, existing["operation_id"])
            self._assert_no_replacement(tx, intent)
            tx.conn.execute("UPDATE ua_delete_confirmations SET operation_id=? WHERE token=?",
                            (intent["operation_id"], token))
            return intent
        row = _row(tx.conn, "SELECT * FROM cars WHERE id=?", (confirmation["car_id"],))
        if row is None:
            raise DeletionError("CAR_MISSING_NO_ORIGINAL_JOB")
        if _snapshot(row) != confirmation["snapshot"]:
            raise DeletionError("STALE_CALLBACK_OPERATOR_CHANGE_PRESERVED")
        if tx.conn.execute("SELECT count(*) FROM cars WHERE id=? OR auto_number=?", (row["id"], row["auto_number"])).fetchone()[0] != 1:
            raise DeletionError("AMBIGUOUS_CURRENT_CAR_CODE")
        self.require_writable(tx, car_id=row["id"], car_code=row["auto_number"], vin=row.get("vin"))
        encoded_plan = self._plan(plan, row)
        _hash(backup_sha256)
        operation_id = secrets.token_hex(32)
        expected = dict(row, published=0)
        expected_snapshot = _snapshot(expected)
        # UPDATE triggers can also touch unrelated rows, so admission must
        # remain uninstalled until the live schema passes this narrow policy.
        self._safe_delete_schema(tx.conn)
        tx.conn.execute("INSERT INTO ua_delete_intents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'REQUESTED',NULL,NULL)",
                        (operation_id, row["id"], row["auto_number"], canonical_vin(row.get("vin")),
                         actor_id, confirmation["snapshot"], confirmation["snapshot_sha256"],
                         expected_snapshot, _sha(expected_snapshot), encoded_plan, _sha(encoded_plan), backup_sha256))
        tx.conn.execute("INSERT INTO ua_delete_jobs VALUES (?,'PENDING')", (operation_id,))
        tx.conn.execute("UPDATE cars SET published=0 WHERE id=?", (row["id"],))
        if _snapshot(_row(tx.conn, "SELECT * FROM cars WHERE id=?", (row["id"],))) != expected_snapshot:
            raise DeletionError("ADMISSION_ROW_CAS_FAILED")
        tx.conn.execute("UPDATE ua_delete_confirmations SET operation_id=? WHERE token=?", (operation_id, token))
        return self._job(tx, operation_id)

    @staticmethod
    def _assert_no_replacement(tx, intent):
        rows = tx.conn.execute("SELECT * FROM cars WHERE id=? OR auto_number=?", (intent["car_id"], intent["car_code"]))
        columns = [d[0] for d in rows.description]
        for row in rows:
            if intent["state"] in ("ROW_DELETED", "COMPLETE"):
                raise DeletionError("ROW_REAPPEARED_AFTER_FINALIZATION")
            if _snapshot(dict(zip(columns, row))) != intent["expected_snapshot"]:
                raise DeletionError("NEWER_CAR_IDENTITY_PRESERVED")

    def _verify(self, intent, proof):
        """Shape and binding checks supplement, never replace, live verification."""
        if not isinstance(proof, dict):
            raise DeletionError("EXACT_RETIREMENT_PROOF_REQUIRED")
        for field in ("operation_id", "car_id", "car_code", "vin", "snapshot_sha256", "expected_snapshot_sha256", "plan_sha256"):
            if proof.get(field) != intent[field]:
                raise DeletionError("RETIREMENT_PROOF_BINDING_MISMATCH:" + field)
        plan = json.loads(intent["plan"])
        for field in ("public_targets", "list_surfaces", "media_targets"):
            if proof.get(field) != plan[field]:
                raise DeletionError("RETIREMENT_TARGET_COVERAGE_MISMATCH:" + field)
        if proof.get("all_absent") is not True or proof.get("counters_match") is not True:
            raise DeletionError("PUBLIC_RETIREMENT_INCOMPLETE")
        if self.verify_retirement(dict(intent), json.loads(_json(proof))) is not True:
            raise DeletionError("FRESH_RETIREMENT_VERIFICATION_FAILED")

    @staticmethod
    def _safe_delete_schema(conn):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='cars'").fetchone():
            raise DeletionError("CAR_TRIGGERS_REQUIRE_SEPARATE_REVIEW")
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            quoted = '"' + name.replace('"', '""') + '"'
            for fk in conn.execute("PRAGMA foreign_key_list(" + quoted + ")"):
                if fk[2] == "cars" and fk[6].upper() not in ("NO ACTION", "RESTRICT"):
                    raise DeletionError("CARS_FK_SIDE_EFFECT_REQUIRES_SEPARATE_REVIEW")

    def finalize_row(self, tx, *, operation_id, proof):
        """Retirement first, full-row CAS next; row and job state commit together."""
        self._check(tx)
        intent = self._job(tx, operation_id)
        self._assert_no_replacement(tx, intent)
        self._verify(intent, proof)
        if intent["state"] in ("ROW_DELETED", "COMPLETE"):
            # A row reappearing after deletion is not silently deleted again.
            if tx.conn.execute("SELECT 1 FROM cars WHERE id=? OR auto_number=?",
                               (intent["car_id"], intent["car_code"])).fetchone():
                raise DeletionError("ROW_REAPPEARED_AFTER_FINALIZATION")
            return intent
        self._safe_delete_schema(tx.conn)
        row = _row(tx.conn, "SELECT * FROM cars WHERE id=?", (intent["car_id"],))
        if row is not None:
            if _snapshot(row) != intent["expected_snapshot"]:
                raise DeletionError("ROW_CAS_OPERATOR_CHANGE_PRESERVED")
            changed = tx.conn.execute("DELETE FROM cars WHERE id=? AND auto_number=?",
                                      (intent["car_id"], intent["car_code"])).rowcount
            if changed != 1:
                raise DeletionError("EXACT_ROW_DELETE_FAILED")
        # Missing row is allowed only because _job found the original durable
        # preimage and outbox, and the exact retirement proof passed above.
        encoded = _json(proof)
        tx.conn.execute("UPDATE ua_delete_intents SET state='ROW_DELETED',proof=?,proof_sha256=? WHERE operation_id=? AND state='REQUESTED'",
                        (encoded, _sha(encoded), operation_id))
        tx.conn.execute("UPDATE ua_delete_jobs SET state='ROW_DELETED' WHERE operation_id=? AND state='PENDING'", (operation_id,))
        return self._job(tx, operation_id)

    def complete(self, tx, *, operation_id, proof):
        """Only after fresh HTTP/counters/media read-back may the bot say deleted."""
        self._check(tx)
        intent = self._job(tx, operation_id)
        if intent["state"] not in ("ROW_DELETED", "COMPLETE"):
            raise DeletionError("ROW_FINALIZATION_REQUIRED")
        if tx.conn.execute("SELECT 1 FROM cars WHERE id=? OR auto_number=?", (intent["car_id"], intent["car_code"])).fetchone():
            raise DeletionError("ROW_REAPPEARED_AFTER_FINALIZATION")
        self._verify(intent, proof)
        encoded = _json(proof)
        tx.conn.execute("UPDATE ua_delete_intents SET state='COMPLETE',proof=?,proof_sha256=? WHERE operation_id=?", (encoded, _sha(encoded), operation_id))
        tx.conn.execute("UPDATE ua_delete_jobs SET state='COMPLETE' WHERE operation_id=?", (operation_id,))
        return self._job(tx, operation_id)

    def pending(self, tx):
        """Resume only durable job IDs; never recreate old cars from snapshots."""
        self._check(tx)
        ids = [row[0] for row in tx.conn.execute("SELECT operation_id FROM ua_delete_jobs WHERE state<>'COMPLETE' ORDER BY operation_id")]
        return [self._job(tx, operation_id) for operation_id in ids]
