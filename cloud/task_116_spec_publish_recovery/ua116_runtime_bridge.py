#!/usr/bin/env python3
"""Runtime adapter proposed for installation only after the owner Production gate.

Importing this module performs no write.  ``handle_saved_vin`` starts only the
target card preparation; ``prepare_for_publish_*`` never toggles publication
and returns a fail-closed decision to ``cars_ui``.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping

from recovery_core import (
    ALL_PRIMARY_FIELDS,
    BaseCandidate,
    RecoveryGuardError,
    WorkerHealth,
    canonical_uid,
    missing_public_base_fields,
    normalize_vin,
    plan_base_fill,
    publication_preflight,
    vin_sha256,
)
from spec_revision_store import get_active, initialize, update_heartbeat
from vin_base_spec_service import apply_fill_plan, row_digest
from vin_primary_decoder import decode_primary_candidates


_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}
_threads: dict[str, threading.Thread] = {}


PRIMARY_QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ua116_primary_fill_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    car_uid TEXT NOT NULL,
    vin TEXT NOT NULL,
    vin_sha256 TEXT NOT NULL,
    actor_id INTEGER,
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','APPLIED','NOOP','FAILED','SUPERSEDED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    requested_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    last_error TEXT NOT NULL DEFAULT '',
    receipt_digest TEXT NOT NULL DEFAULT '',
    UNIQUE(car_uid, vin_sha256)
);
CREATE INDEX IF NOT EXISTS ua116_primary_fill_pending
    ON ua116_primary_fill_job(status, requested_at, id);

CREATE TABLE IF NOT EXISTS ua116_vin_reservation (
    vin_sha256 TEXT PRIMARY KEY,
    car_uid TEXT NOT NULL UNIQUE,
    reserved_at TEXT NOT NULL,
    last_verified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ua116_primary_field_provenance (
    card_id INTEGER NOT NULL,
    car_uid TEXT NOT NULL,
    field TEXT NOT NULL,
    vin_sha256 TEXT NOT NULL,
    prior_value TEXT,
    applied_value TEXT NOT NULL,
    receipt_digest TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    PRIMARY KEY(card_id, field)
);
CREATE INDEX IF NOT EXISTS ua116_primary_provenance_active
    ON ua116_primary_field_provenance(car_uid, active, vin_sha256);
"""


def _lock(uid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(uid, threading.Lock())


def _modules():
    import ua_additional_spec
    import vin_spec_service

    return vin_spec_service, ua_additional_spec


def _paths() -> tuple[Path, Path]:
    service, _ = _modules()
    return Path(service.MAIN_DB), Path(service.SPEC_DB)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _error_code(exc: BaseException) -> str:
    return exc.code if isinstance(exc, RecoveryGuardError) else type(exc).__name__


def _initialize_runtime_tables(spec_db: Path) -> None:
    initialize(spec_db)
    with sqlite3.connect(str(spec_db), timeout=15.0) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        con.executescript(PRIMARY_QUEUE_SCHEMA)


def _published_duplicate_uids(
    main_db: Path, *, uid: str, vin: str
) -> tuple[str, ...]:
    normalized_uid, normalized_vin = canonical_uid(uid), normalize_vin(vin)
    with _connect_ro(main_db) as con:
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(cars)")}
        status_clause = (
            "AND LOWER(COALESCE(status,''))<>'archive'" if "status" in columns else ""
        )
        published_clause = "AND COALESCE(published,0)=1" if "published" in columns else ""
        rows = con.execute(
            "SELECT auto_number FROM cars WHERE UPPER(auto_number)<>? "
            "AND UPPER(REPLACE(REPLACE(vin,' ',''),'-',''))=? "
            + published_clause
            + " "
            + status_clause,
            (normalized_uid, normalized_vin),
        ).fetchall()
    return tuple(sorted(canonical_uid(row[0]) for row in rows))


def _attached_main(con: sqlite3.Connection, main_db: Path) -> None:
    """Attach the CRM database before BEGIN so SQLite locks both databases."""

    con.execute("ATTACH DATABASE ? AS ua116_main", (str(main_db.resolve()),))


def _published_duplicate_uids_attached(
    con: sqlite3.Connection, *, uid: str, vin: str
) -> tuple[str, ...]:
    columns = {
        str(row[1]) for row in con.execute("PRAGMA ua116_main.table_info(cars)")
    }
    status_clause = (
        "AND LOWER(COALESCE(status,''))<>'archive'" if "status" in columns else ""
    )
    published_clause = (
        "AND COALESCE(published,0)=1" if "published" in columns else ""
    )
    rows = con.execute(
        "SELECT auto_number FROM ua116_main.cars WHERE UPPER(auto_number)<>? "
        "AND UPPER(REPLACE(REPLACE(vin,' ',''),'-',''))=? "
        + published_clause
        + " "
        + status_clause,
        (canonical_uid(uid), normalize_vin(vin)),
    ).fetchall()
    return tuple(sorted(canonical_uid(row[0]) for row in rows))


def reserve_vin(*, uid: str, vin: str) -> dict[str, Any]:
    """Reserve one normalized VIN for one UID across bot processes.

    The reservation is deliberately durable.  A retry for the same card is a
    no-op; a different card fails before enrichment or primary-field writes.
    """

    main_db, spec_db = _paths()
    uid, vin = canonical_uid(uid), normalize_vin(vin)
    _initialize_runtime_tables(spec_db)
    now = _utc_now()
    digest = vin_sha256(vin)
    with sqlite3.connect(str(spec_db), timeout=15.0, isolation_level=None) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        _attached_main(con, main_db)
        con.execute("BEGIN IMMEDIATE")
        target = con.execute(
            "SELECT vin FROM ua116_main.cars WHERE UPPER(auto_number)=? LIMIT 2",
            (uid,),
        ).fetchall()
        if len(target) != 1:
            raise RecoveryGuardError(
                "CARD_NOT_FOUND" if not target else "DUPLICATE_CARD_UID", uid
            )
        if normalize_vin(target[0][0]) != vin:
            raise RecoveryGuardError("CARD_VIN_CHANGED")
        duplicates = _published_duplicate_uids_attached(con, uid=uid, vin=vin)
        if duplicates:
            raise RecoveryGuardError("DUPLICATE_ACTIVE_VIN", ",".join(duplicates))
        owner = con.execute(
            "SELECT car_uid FROM ua116_vin_reservation WHERE vin_sha256=?",
            (digest,),
        ).fetchone()
        if owner and canonical_uid(owner[0]) != uid:
            raise RecoveryGuardError("VIN_RESERVED_BY_OTHER_CARD", canonical_uid(owner[0]))
        # A card may have only its current VIN reservation.  This makes a VIN
        # correction idempotent without leaving a stale self-reservation.
        con.execute(
            "DELETE FROM ua116_vin_reservation WHERE car_uid=? AND vin_sha256<>?",
            (uid, digest),
        )
        con.execute(
            "INSERT INTO ua116_vin_reservation(vin_sha256,car_uid,reserved_at,last_verified_at) "
            "VALUES(?,?,?,?) ON CONFLICT(vin_sha256) DO UPDATE SET "
            "last_verified_at=excluded.last_verified_at WHERE car_uid=excluded.car_uid",
            (digest, uid, now, now),
        )
        con.commit()
    return {"uid": uid, "vin_sha256": digest, "status": "RESERVED"}


def bootstrap_published_vin_reservations() -> dict[str, Any]:
    """Fail-closed bootstrap used before the future runtime cutover."""

    main_db, spec_db = _paths()
    _initialize_runtime_tables(spec_db)
    now = _utc_now()
    with sqlite3.connect(str(spec_db), timeout=15.0, isolation_level=None) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        _attached_main(con, main_db)
        con.execute("BEGIN IMMEDIATE")
        columns = {
            str(row[1]) for row in con.execute("PRAGMA ua116_main.table_info(cars)")
        }
        status_clause = (
            "AND LOWER(COALESCE(status,''))<>'archive'" if "status" in columns else ""
        )
        published_clause = "COALESCE(published,0)=1" if "published" in columns else "1=1"
        rows = con.execute(
            "SELECT auto_number,vin FROM ua116_main.cars WHERE "
            + published_clause
            + " "
            + status_clause
            + " ORDER BY auto_number"
        ).fetchall()
        grouped: dict[str, list[str]] = {}
        normalized: list[tuple[str, str, str]] = []
        for row in rows:
            uid, vin = canonical_uid(row[0]), normalize_vin(row[1])
            digest = vin_sha256(vin)
            grouped.setdefault(digest, []).append(uid)
            normalized.append((uid, vin, digest))
        collisions = {
            key: value for key, value in grouped.items() if len(set(value)) > 1
        }
        if collisions:
            raise RecoveryGuardError(
                "DUPLICATE_ACTIVE_VIN_BOOTSTRAP",
                ";".join(",".join(sorted(set(value))) for value in collisions.values()),
            )
        for uid, _vin, digest in normalized:
            owner = con.execute(
                "SELECT car_uid FROM ua116_vin_reservation WHERE vin_sha256=?",
                (digest,),
            ).fetchone()
            if owner and canonical_uid(owner[0]) != uid:
                raise RecoveryGuardError("VIN_RESERVATION_BOOTSTRAP_CONFLICT", uid)
            con.execute(
                "INSERT INTO ua116_vin_reservation(vin_sha256,car_uid,reserved_at,last_verified_at) "
                "VALUES(?,?,?,?) ON CONFLICT(vin_sha256) DO UPDATE SET "
                "last_verified_at=excluded.last_verified_at WHERE car_uid=excluded.car_uid",
                (digest, uid, now, now),
            )
        con.commit()
    return {"status": "PASS", "reserved": len(normalized)}


def _connect_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=15.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def _full_card_by_id(path: Path, card_id: int) -> dict[str, Any] | None:
    with _connect_ro(path) as con:
        row = con.execute("SELECT * FROM cars WHERE id=?", (int(card_id),)).fetchone()
        return dict(row) if row else None


def _full_card_by_uid(path: Path, uid: str) -> dict[str, Any] | None:
    with _connect_ro(path) as con:
        row = con.execute(
            "SELECT * FROM cars WHERE UPPER(auto_number)=?", (canonical_uid(uid),)
        ).fetchone()
        return dict(row) if row else None


def enqueue_primary_fill(
    *, card_id: int, uid: str, vin: str, actor_id: int | None
) -> dict[str, Any]:
    """Persist an idempotent primary-fill job before background work starts."""

    main_db, spec_db = _paths()
    _initialize_runtime_tables(spec_db)
    uid, vin = canonical_uid(uid), normalize_vin(vin)
    digest, now = vin_sha256(vin), _utc_now()
    with sqlite3.connect(str(spec_db), timeout=15.0, isolation_level=None) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        _attached_main(con, main_db)
        con.execute("BEGIN IMMEDIATE")
        current = con.execute(
            "SELECT id,auto_number,vin FROM ua116_main.cars WHERE id=?",
            (int(card_id),),
        ).fetchone()
        if current is None:
            raise RecoveryGuardError("CARD_NOT_FOUND", str(card_id))
        if canonical_uid(current["auto_number"]) != uid:
            raise RecoveryGuardError("CARD_UID_CHANGED")
        if normalize_vin(current["vin"]) != vin:
            raise RecoveryGuardError("CARD_VIN_CHANGED")
        con.execute(
            "UPDATE ua116_primary_fill_job SET status='SUPERSEDED',finished_at=? "
            "WHERE car_uid=? AND vin_sha256<>? AND status IN ('PENDING','RUNNING','FAILED')",
            (now, uid, digest),
        )
        con.execute(
            "INSERT INTO ua116_primary_fill_job "
            "(card_id,car_uid,vin,vin_sha256,actor_id,status,requested_at) "
            "VALUES(?,?,?,?,?,'PENDING',?) ON CONFLICT(car_uid,vin_sha256) DO UPDATE SET "
            "card_id=excluded.card_id,actor_id=COALESCE(excluded.actor_id,actor_id),"
            "requested_at=excluded.requested_at,status=CASE "
            "WHEN status='RUNNING' THEN status ELSE 'PENDING' END,"
            "attempts=CASE WHEN status='RUNNING' THEN attempts ELSE 0 END,"
            "started_at=CASE WHEN status='RUNNING' THEN started_at ELSE NULL END,"
            "finished_at=CASE WHEN status='RUNNING' THEN finished_at ELSE NULL END,"
            "last_error=CASE WHEN status='RUNNING' THEN last_error ELSE '' END,"
            "receipt_digest=CASE WHEN status='RUNNING' THEN receipt_digest ELSE '' END",
            (int(card_id), uid, vin, digest, actor_id, now),
        )
        row = con.execute(
            "SELECT * FROM ua116_primary_fill_job WHERE car_uid=? AND vin_sha256=?",
            (uid, digest),
        ).fetchone()
        con.commit()
    return dict(row)


def _claim_primary_job(uid: str | None = None) -> dict[str, Any] | None:
    _main_db, spec_db = _paths()
    _initialize_runtime_tables(spec_db)
    with sqlite3.connect(str(spec_db), timeout=15.0, isolation_level=None) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        con.execute("BEGIN IMMEDIATE")
        params: tuple[Any, ...] = ()
        where = "status IN ('PENDING','FAILED') AND attempts<5"
        if uid is not None:
            where += " AND car_uid=?"
            params = (canonical_uid(uid),)
        row = con.execute(
            "SELECT * FROM ua116_primary_fill_job WHERE " + where + " ORDER BY id LIMIT 1",
            params,
        ).fetchone()
        if row is None:
            con.commit()
            return None
        changed = con.execute(
            "UPDATE ua116_primary_fill_job SET status='RUNNING',attempts=attempts+1,"
            "started_at=?,last_error='' WHERE id=? AND status IN ('PENDING','FAILED')",
            (_utc_now(), int(row["id"])),
        )
        if changed.rowcount != 1:
            con.rollback()
            return None
        claimed = con.execute(
            "SELECT * FROM ua116_primary_fill_job WHERE id=?", (int(row["id"]),)
        ).fetchone()
        con.commit()
    return dict(claimed)


def _finish_primary_job(
    job_id: int, *, status: str, error: str = "", receipt_digest: str = ""
) -> str:
    if status not in {"APPLIED", "NOOP", "FAILED", "SUPERSEDED"}:
        raise ValueError("PRIMARY_JOB_STATUS")
    _main_db, spec_db = _paths()
    with sqlite3.connect(str(spec_db), timeout=15.0, isolation_level=None) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT status FROM ua116_primary_fill_job WHERE id=?", (int(job_id),)
        ).fetchone()
        if row is None:
            raise RecoveryGuardError("PRIMARY_JOB_NOT_FOUND", str(job_id))
        current_status = str(row["status"])
        if current_status != "RUNNING":
            # A VIN correction is allowed to supersede an in-flight job.  Its
            # worker must observe that terminal state instead of overwriting it
            # or raising a second, misleading FAILED transition.
            if current_status == status or current_status == "SUPERSEDED":
                con.commit()
                return current_status
            raise RecoveryGuardError(
                "PRIMARY_JOB_FINISH_CONFLICT", "%s:%s" % (job_id, current_status)
            )
        changed = con.execute(
            "UPDATE ua116_primary_fill_job SET status=?,finished_at=?,last_error=?,"
            "receipt_digest=? WHERE id=? AND status='RUNNING'",
            (status, _utc_now(), str(error)[:500], str(receipt_digest), int(job_id)),
        )
        if changed.rowcount != 1:
            raise RecoveryGuardError("PRIMARY_JOB_FINISH_CONFLICT", str(job_id))
        con.commit()
    return status


def _primary_job_state(uid: str, vin: str) -> dict[str, Any] | None:
    _main_db, spec_db = _paths()
    _initialize_runtime_tables(spec_db)
    with _connect_ro(spec_db) as con:
        row = con.execute(
            "SELECT * FROM ua116_primary_fill_job WHERE car_uid=? AND vin_sha256=?",
            (canonical_uid(uid), vin_sha256(vin)),
        ).fetchone()
    return dict(row) if row else None


def _record_primary_provenance(
    *, card_id: int, uid: str, vin: str, receipt: Mapping[str, Any]
) -> None:
    """Durably bind every TASK116 primary write to its source VIN."""

    fields = tuple(sorted(str(item) for item in receipt.get("written_fields", ())))
    if not fields:
        return
    if any(field not in ALL_PRIMARY_FIELDS for field in fields):
        raise RecoveryGuardError("PRIMARY_PROVENANCE_FIELD")
    main_db, spec_db = _paths()
    digest, now = vin_sha256(vin), _utc_now()
    with sqlite3.connect(str(spec_db), timeout=15.0, isolation_level=None) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        _attached_main(con, main_db)
        con.execute("BEGIN IMMEDIATE")
        card = con.execute(
            "SELECT * FROM ua116_main.cars WHERE id=?", (int(card_id),)
        ).fetchone()
        if card is None or canonical_uid(card["auto_number"]) != canonical_uid(uid):
            raise RecoveryGuardError("CARD_UID_CHANGED")
        if normalize_vin(card["vin"]) != normalize_vin(vin):
            raise RecoveryGuardError("CARD_VIN_CHANGED")
        for field in fields:
            audit = con.execute(
                "SELECT old_value,new_value FROM ua116_main.audit "
                "WHERE entity_type='cars' AND entity_id=? AND field=? "
                "AND action LIKE 'vin_base_spec_empty_only %' ORDER BY id DESC LIMIT 1",
                (int(card_id), field),
            ).fetchone()
            if audit is None or str(card[field] or "") != str(audit["new_value"] or ""):
                raise RecoveryGuardError("PRIMARY_PROVENANCE_READBACK", field)
            con.execute(
                "INSERT INTO ua116_primary_field_provenance "
                "(card_id,car_uid,field,vin_sha256,prior_value,applied_value,"
                "receipt_digest,recorded_at,active) VALUES(?,?,?,?,?,?,?,?,1) "
                "ON CONFLICT(card_id,field) DO UPDATE SET "
                "car_uid=excluded.car_uid,vin_sha256=excluded.vin_sha256,"
                "prior_value=excluded.prior_value,applied_value=excluded.applied_value,"
                "receipt_digest=excluded.receipt_digest,recorded_at=excluded.recorded_at,active=1",
                (
                    int(card_id), canonical_uid(uid), field, digest,
                    audit["old_value"], str(audit["new_value"]),
                    str(receipt.get("receipt_digest") or ""), now,
                ),
            )
        con.commit()


def _reconcile_primary_provenance(
    *, card_id: int, uid: str, vin: str, actor_id: int | None
) -> tuple[str, ...]:
    """Restore only unchanged TASK116 values when a card's VIN is corrected."""

    main_db, spec_db = _paths()
    _initialize_runtime_tables(spec_db)
    current_digest, now = vin_sha256(vin), _utc_now()
    restored: list[str] = []
    with sqlite3.connect(str(spec_db), timeout=15.0, isolation_level=None) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        _attached_main(con, main_db)
        con.execute("BEGIN IMMEDIATE")
        card = con.execute(
            "SELECT * FROM ua116_main.cars WHERE id=?", (int(card_id),)
        ).fetchone()
        if card is None or canonical_uid(card["auto_number"]) != canonical_uid(uid):
            raise RecoveryGuardError("CARD_UID_CHANGED")
        if normalize_vin(card["vin"]) != normalize_vin(vin):
            raise RecoveryGuardError("CARD_VIN_CHANGED")
        rows = con.execute(
            "SELECT field,vin_sha256,prior_value,applied_value FROM "
            "ua116_primary_field_provenance WHERE card_id=? AND car_uid=? "
            "AND active=1 AND vin_sha256<>? ORDER BY field",
            (int(card_id), canonical_uid(uid), current_digest),
        ).fetchall()
        for row in rows:
            field = str(row["field"])
            if field not in ALL_PRIMARY_FIELDS:
                raise RecoveryGuardError("PRIMARY_PROVENANCE_FIELD", field)
            if str(card[field] or "") == str(row["applied_value"] or ""):
                changed = con.execute(
                    'UPDATE ua116_main.cars SET "' + field + '"=? WHERE id=? '
                    'AND COALESCE(CAST("' + field + '" AS TEXT),\'\')=?',
                    (row["prior_value"], int(card_id), str(row["applied_value"])),
                )
                if changed.rowcount != 1:
                    raise RecoveryGuardError("PRIMARY_CORRECTION_CAS", field)
                con.execute(
                    "INSERT INTO ua116_main.audit "
                    "(actor_id,action,entity_type,entity_id,field,old_value,new_value,created_at) "
                    "VALUES(?,?,'cars',?,?,?,?,?)",
                    (
                        actor_id,
                        "ua116_vin_correction_restore " + str(row["vin_sha256"]),
                        int(card_id), field, row["applied_value"], row["prior_value"], now,
                    ),
                )
                restored.append(field)
            con.execute(
                "UPDATE ua116_primary_field_provenance SET active=0 "
                "WHERE card_id=? AND field=? AND vin_sha256=? AND active=1",
                (int(card_id), field, str(row["vin_sha256"])),
            )
        con.commit()
    return tuple(restored)


def _same_vin_candidates(
    path: Path, *, card_id: int, vin: str
) -> tuple[list[BaseCandidate], tuple[str, ...]]:
    wanted_hash = vin_sha256(vin)
    fields = (
        "brand",
        "model",
        "year",
        "trim",
        "body",
        "fuel",
        "engine",
        "engine_cc",
        "gearbox",
        "drive",
        "mileage",
        "mileage_km",
        "color",
    )
    with _connect_ro(path) as con:
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(cars)")}
        selected = [field for field in fields if field in columns]
        rows = con.execute(
            "SELECT id,auto_number,published,status,"
            + ",".join('"' + field + '"' for field in selected)
            + " FROM cars WHERE id<>? "
            "AND UPPER(REPLACE(REPLACE(vin,' ',''),'-',''))=?",
            (int(card_id), str(vin).upper().replace(" ", "").replace("-", "")),
        ).fetchall()
    candidates: list[BaseCandidate] = []
    for field in selected:
        values = {str(row[field]).strip() for row in rows if str(row[field] or "").strip()}
        # Conflicting historical rows are never guessed.
        if len(values) == 1:
            candidates.append(
                BaseCandidate(
                    field=field,
                    value=next(iter(values)),
                    source_kind="same_vin_crm",
                    source="crm:same-vin",
                    confidence=0.99,
                    vin_sha256=wanted_hash,
                )
            )
    duplicates = tuple(
        sorted(
            canonical_uid(row["auto_number"])
            for row in rows
            if int(row["published"] or 0) == 1
            and str(row["status"] or "") != "archive"
        )
    )
    return candidates, duplicates


def _active_for_exact_vin(uid: str, vin: str):
    """Return only an already validated snapshot bound to this exact VIN."""

    _, spec_db = _paths()
    active = get_active(spec_db, uid)
    if active is None or active.vin_sha256 != vin_sha256(vin):
        return None
    return active


def _heartbeat(instance: str, *, error: str = "", success: bool = False) -> WorkerHealth:
    _, spec_db = _paths()
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    update_heartbeat(
        spec_db,
        worker_instance_id=instance,
        worker_started_at=now,
        last_cycle_at=now,
        last_success_at=now if success else "",
        last_cycle_error=error,
        queue_depth=0,
    )
    return WorkerHealth(instance, now, now if success else "", error, 0)


def _fill_base(card: Mapping[str, Any], *, actor_id: int | None) -> dict[str, Any]:
    main_db, _ = _paths()
    uid = canonical_uid(card["auto_number"])
    vin = normalize_vin(card["vin"])
    candidates, duplicates = _same_vin_candidates(
        main_db, card_id=int(card["id"]), vin=vin
    )
    if duplicates:
        raise RecoveryGuardError("DUPLICATE_ACTIVE_VIN", ",".join(duplicates))
    try:
        candidates.extend(decode_primary_candidates(vin))
    except Exception:
        # Same-VIN CRM evidence may still safely fill the card; a decoder
        # outage never permits invented values.
        pass
    current = _full_card_by_id(main_db, int(card["id"]))
    if current is None:
        raise RuntimeError("CARD_NOT_FOUND")
    if canonical_uid(current.get("auto_number")) != uid:
        raise RecoveryGuardError("CARD_UID_CHANGED")
    if normalize_vin(current.get("vin")) != vin:
        raise RecoveryGuardError("CARD_VIN_CHANGED")
    plan = plan_base_fill(current, candidates, expected_vin=vin)
    if not plan.writes:
        return {"status": "NOOP", "written_fields": []}
    return apply_fill_plan(
        main_db,
        card_id=int(card["id"]),
        uid=uid,
        expected_vin=vin,
        plan=plan,
        actor_id=actor_id,
        expected_row_digest=row_digest(current),
        allow_production=True,
    )


def process_pending_primary_jobs(*, limit: int = 1, uid: str | None = None) -> list[dict[str, Any]]:
    """Durably retry primary-spec fills; safe to call from the existing worker."""

    main_db, _spec_db = _paths()
    results: list[dict[str, Any]] = []
    for _ in range(max(0, int(limit))):
        job = _claim_primary_job(uid)
        if job is None:
            break
        job_id = int(job["id"])
        try:
            card = _full_card_by_id(main_db, int(job["card_id"]))
            if card is None:
                raise RecoveryGuardError("CARD_NOT_FOUND")
            if canonical_uid(card.get("auto_number")) != canonical_uid(job["car_uid"]):
                raise RecoveryGuardError("CARD_UID_CHANGED")
            if normalize_vin(card.get("vin")) != normalize_vin(job["vin"]):
                final_status = _finish_primary_job(job_id, status="SUPERSEDED")
                results.append({"id": job_id, "status": final_status})
                continue
            reserve_vin(uid=job["car_uid"], vin=job["vin"])
            receipt = _fill_base(card, actor_id=job.get("actor_id"))
            _record_primary_provenance(
                card_id=int(job["card_id"]),
                uid=str(job["car_uid"]),
                vin=str(job["vin"]),
                receipt=receipt,
            )
            final = "APPLIED" if receipt.get("status") == "APPLIED" else "NOOP"
            latest = _full_card_by_id(main_db, int(job["card_id"]))
            if (
                latest is None
                or canonical_uid(latest.get("auto_number"))
                != canonical_uid(job["car_uid"])
                or normalize_vin(latest.get("vin")) != normalize_vin(job["vin"])
            ):
                final = "SUPERSEDED"
            final_status = _finish_primary_job(
                job_id,
                status=final,
                receipt_digest=str(receipt.get("receipt_digest") or ""),
            )
            results.append({"id": job_id, "status": final_status, "receipt": receipt})
        except Exception as exc:
            try:
                final_status = _finish_primary_job(
                    job_id,
                    status="FAILED",
                    error=type(exc).__name__ + ":" + str(exc),
                )
            except RecoveryGuardError as finish_exc:
                final_status = "FINISH_CONFLICT"
                exc = finish_exc
            results.append(
                {"id": job_id, "status": final_status, "error": type(exc).__name__}
            )
    return results


def _require_primary_complete(
    uid: str, vin: str, *, card_id: int
) -> dict[str, Any]:
    job = _primary_job_state(uid, vin)
    status = str((job or {}).get("status") or "NOT_QUEUED")
    if status not in {"APPLIED", "NOOP"}:
        raise RecoveryGuardError("PRIMARY_FILL_NOT_COMPLETE", status)
    main_db, _spec_db = _paths()
    card = _full_card_by_id(main_db, int(card_id))
    if card is None:
        raise RecoveryGuardError("CARD_NOT_FOUND", str(card_id))
    if canonical_uid(card.get("auto_number")) != canonical_uid(uid):
        raise RecoveryGuardError("CARD_UID_CHANGED")
    if normalize_vin(card.get("vin")) != normalize_vin(vin):
        raise RecoveryGuardError("CARD_VIN_CHANGED")
    missing = missing_public_base_fields(card)
    if missing:
        raise RecoveryGuardError("BASE_SPEC_INCOMPLETE", ",".join(missing))
    return dict(job or {})


def _service_card_exact(service: Any, *, card_id: int, uid: str, vin: str) -> Mapping[str, Any]:
    for item in service.read_cards():
        if int(item.get("car_id") or 0) != int(card_id):
            continue
        if canonical_uid(item.get("car_uid")) != canonical_uid(uid):
            raise RecoveryGuardError("VIN_SERVICE_UID_MISMATCH")
        if normalize_vin(item.get("vin")) != normalize_vin(vin):
            raise RecoveryGuardError("VIN_SERVICE_VIN_MISMATCH")
        return item
    raise RecoveryGuardError("VIN_SERVICE_CARD_NOT_FOUND", str(card_id))


def _require_exact_service_state(state: Mapping[str, Any] | None, vin: str) -> str:
    status = str((state or {}).get("status") or "NOT_QUEUED")
    state_vin = str((state or {}).get("vin") or "")
    if not state_vin or normalize_vin(state_vin) != normalize_vin(vin):
        raise RecoveryGuardError("VIN_JOB_NOT_EXACT")
    return status


def _prepare_card(card_id: int, vin: str, actor_id: int | None) -> dict[str, Any]:
    service, _ = _modules()
    main_db, _spec_db = _paths()
    card = _full_card_by_id(main_db, card_id)
    if card is None:
        raise RuntimeError("CARD_NOT_FOUND")
    uid = canonical_uid(card["auto_number"])
    vin = normalize_vin(vin)
    if normalize_vin(card.get("vin")) != vin:
        raise RecoveryGuardError("CARD_VIN_CHANGED")
    instance = "task116-target:%s:%s" % (os.getpid(), uuid.uuid4().hex[:10])
    with _lock(uid):
        _heartbeat(instance)
        try:
            reservation = reserve_vin(uid=uid, vin=vin)
            enqueue_primary_fill(
                card_id=card_id, uid=uid, vin=vin, actor_id=actor_id
            )
            base_results = process_pending_primary_jobs(limit=1, uid=uid)
            _require_primary_complete(uid, vin, card_id=card_id)
            current = _service_card_exact(
                service, card_id=card_id, uid=uid, vin=vin
            )
            service.enqueue_card(current)
            outcome = service.process_card_now(uid)
            if outcome is None:
                outcome = service.card_state(uid)
            _require_exact_service_state(outcome, vin)
            active = _active_for_exact_vin(uid, vin)
            outcome_status = str((outcome or {}).get("status") or "PENDING")
            _heartbeat(instance, success=outcome_status == "READY" and active is not None)
            return {
                "contract_id": "UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001",
                "mode": "RUNTIME_PREPARATION",
                "status": outcome_status,
                "target_uid": uid,
                "target_vin_sha256": vin_sha256(vin),
                "vin_reservation": reservation,
                "primary_fill_results": base_results,
                "primary_crm_write": any(
                    item.get("status") == "APPLIED" for item in base_results
                ),
                "sidecar_write": True,
                "spec_revision_id": active.revision_id if active else "",
                "visible_spec_rows": active.visible_count if active else 0,
                "finished_at": _utc_now(),
            }
        except Exception as exc:
            _heartbeat(instance, error=type(exc).__name__ + ":" + str(exc))
            raise


def handle_saved_vin(*, card_id: int, vin: str, actor_id: int | None) -> dict[str, Any]:
    """Synchronously fill primary fields, then start additional enrichment."""

    main_db, _ = _paths()
    card = _full_card_by_id(main_db, card_id)
    if card is None:
        return {"status": "CARD_NOT_FOUND", "owner_text": "карточка не найдена"}
    uid = canonical_uid(card["auto_number"])
    try:
        vin = normalize_vin(vin)
        if normalize_vin(card.get("vin")) != vin:
            raise RecoveryGuardError("CARD_VIN_CHANGED")
        _reconcile_primary_provenance(
            card_id=card_id, uid=uid, vin=vin, actor_id=actor_id
        )
        reservation = reserve_vin(uid=uid, vin=vin)
        enqueue_primary_fill(card_id=card_id, uid=uid, vin=vin, actor_id=actor_id)
        base_results = process_pending_primary_jobs(limit=1, uid=uid)
        _require_primary_complete(uid, vin, card_id=card_id)
        service, _renderer = _modules()
        current = _service_card_exact(
            service, card_id=card_id, uid=uid, vin=vin
        )
        service.enqueue_card(current)
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "code": _error_code(exc),
            "owner_text": "VIN записан, но подготовка заблокирована: %s" % str(exc),
        }
    with _locks_guard:
        thread = _threads.get(uid)
        if thread and thread.is_alive():
            return {"status": "RUNNING", "owner_text": "подготовка уже выполняется"}
        thread = threading.Thread(
            target=_prepare_card,
            kwargs={"card_id": int(card_id), "vin": vin, "actor_id": actor_id},
            name="task116-vin-" + uid,
            daemon=True,
        )
        _threads[uid] = thread
        thread.start()
    return {
        "status": "PENDING",
        "owner_text": "основная спецификация заполнена, дополнительная подготовка запущена",
        "vin_reservation": reservation,
        "primary_fill_results": base_results,
    }


def _job_state(uid: str) -> Mapping[str, Any]:
    service, _ = _modules()
    return service.card_state(uid)


def _read_worker_health() -> WorkerHealth | None:
    _main_db, spec_db = _paths()
    candidates: list[WorkerHealth] = []
    with _connect_ro(spec_db) as con:
        tables = {
            str(row[0])
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "vin_spec_state" in tables:
            values = {
                str(row["key"]): str(row["value"] or "")
                for row in con.execute(
                    "SELECT key,value FROM vin_spec_state WHERE key IN "
                    "('worker_instance_id','last_cycle_at','last_success_at',"
                    "'last_cycle_error','queue_depth')"
                )
            }
            if values.get("last_cycle_at"):
                try:
                    depth = int(values.get("queue_depth") or 0)
                except ValueError:
                    depth = 0
                candidates.append(
                    WorkerHealth(
                        values.get("worker_instance_id", ""),
                        values.get("last_cycle_at", ""),
                        values.get("last_success_at", ""),
                        values.get("last_cycle_error", ""),
                        depth,
                    )
                )
        if "ua116_worker_heartbeat" in tables:
            row = con.execute(
                "SELECT * FROM ua116_worker_heartbeat WHERE singleton=1"
            ).fetchone()
            if row:
                candidates.append(
                    WorkerHealth(
                        str(row["worker_instance_id"]),
                        str(row["last_cycle_at"]),
                        str(row["last_success_at"]),
                        str(row["last_cycle_error"]),
                        int(row["queue_depth"] or 0),
                    )
                )
    valid: list[tuple[dt.datetime, WorkerHealth]] = []
    for candidate in candidates:
        if not candidate.worker_instance_id:
            continue
        try:
            observed = dt.datetime.fromisoformat(
                candidate.last_cycle_at.replace("Z", "+00:00")
            )
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=dt.timezone.utc)
            observed = observed.astimezone(dt.timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        valid.append((observed, candidate))
    if not valid:
        return None
    # A successful synchronous TASK116 preparation is real worker evidence.
    # It must not be hidden merely because the older legacy table exists.
    return max(valid, key=lambda item: item[0])[1]


def prepare_for_publish(card: Mapping[str, Any]) -> dict[str, Any]:
    """Synchronous readiness gate.  It never calls a publisher."""

    service, _ = _modules()
    main_db, _ = _paths()
    uid = canonical_uid(card["auto_number"])
    vin = normalize_vin(card["vin"])
    latest = _full_card_by_uid(main_db, uid)
    if latest is None:
        return {"ok": False, "code": "CARD_NOT_FOUND", "owner_text": "Карточка не найдена."}
    try:
        if normalize_vin(latest.get("vin")) != vin:
            raise RecoveryGuardError("CARD_VIN_CHANGED")
        _reconcile_primary_provenance(
            card_id=int(latest["id"]), uid=uid, vin=vin, actor_id=None
        )
        reservation = reserve_vin(uid=uid, vin=vin)
        enqueue_primary_fill(
            card_id=int(latest["id"]), uid=uid, vin=vin, actor_id=None
        )
        base_results = process_pending_primary_jobs(limit=1, uid=uid)
        _require_primary_complete(uid, vin, card_id=int(latest["id"]))
        latest = _full_card_by_uid(main_db, uid)
        if latest is None or normalize_vin(latest.get("vin")) != vin:
            raise RecoveryGuardError("CARD_VIN_CHANGED")
        current = _service_card_exact(
            service, card_id=int(latest["id"]), uid=uid, vin=vin
        )
        service.enqueue_card(current)
        state = _job_state(uid)
        if str(state.get("status") or "") != "READY":
            processed = service.process_card_now(uid)
            state = processed or _job_state(uid)
        job_status = _require_exact_service_state(state, vin)
        active = _active_for_exact_vin(uid, vin)
        _same, duplicates = _same_vin_candidates(
            main_db, card_id=int(latest["id"]), vin=vin
        )
        if duplicates:
            raise RecoveryGuardError("DUPLICATE_ACTIVE_VIN", ",".join(duplicates))
        heartbeat_instance = "task116-publish:%s:%s" % (os.getpid(), uuid.uuid4().hex[:10])
        _heartbeat(
            heartbeat_instance,
            success=job_status == "READY" and active is not None,
            error="" if job_status == "READY" else "VIN_JOB_" + job_status,
        )
        now = dt.datetime.now(dt.timezone.utc)
        heartbeat = _read_worker_health()
        preflight = publication_preflight(
            uid=uid,
            vin=vin,
            card=latest,
            active_spec=active,
            worker_health=heartbeat,
            duplicate_active_uids=duplicates,
            now=now,
        )
        ok = preflight.ok and job_status == "READY"
        codes = list(preflight.codes)
        if job_status != "READY":
            codes.insert(0, "VIN_JOB_" + job_status)
        return {
            "ok": ok,
            "code": "READY" if ok else (codes[0] if codes else "NOT_READY"),
            "codes": codes,
            "owner_text": (
                "Спецификация готова."
                if ok
                else "Публикация не выполнена. Подготовка VIN: %s. Карточка и сайт не изменены."
                % "; ".join(codes)
            ),
            "visible_spec_rows": preflight.visible_spec_rows,
            "spec_revision_id": preflight.spec_revision_id,
            "vin_reservation": reservation,
            "primary_fill_results": base_results,
        }
    except Exception as exc:
        code = _error_code(exc)
        return {
            "ok": False,
            "code": code,
            "codes": [code],
            "owner_text": "Публикация не выполнена. Подготовка VIN требует проверки: %s. Сайт не изменён."
            % code,
        }


async def prepare_for_publish_async(card: Mapping[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(prepare_for_publish, dict(card))
