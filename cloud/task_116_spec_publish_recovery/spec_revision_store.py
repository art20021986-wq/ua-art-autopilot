#!/usr/bin/env python3
"""Revisioned, non-destructive storage for additional specifications.

Candidates are written separately and become ACTIVE only after validation.
An empty/partial refresh can therefore never erase the last good snapshot.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from recovery_core import (
    PUBLIC_MIN_VISIBLE_SPEC_ROWS,
    RecoveryGuardError,
    SpecFact,
    SpecRevision,
    assert_spec_revision_integrity,
    build_candidate_revision,
    canonical_uid,
    vin_sha256,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS ua116_spec_revision (
    revision_id TEXT PRIMARY KEY,
    car_uid TEXT NOT NULL,
    vin_sha256 TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('CANDIDATE','ACTIVE','ARCHIVED','REJECTED')),
    visible_count INTEGER NOT NULL,
    digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    activated_at TEXT,
    reject_code TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ua116_one_active_revision
    ON ua116_spec_revision(car_uid) WHERE status='ACTIVE';
CREATE INDEX IF NOT EXISTS ua116_revision_lookup
    ON ua116_spec_revision(car_uid, vin_sha256, status);

CREATE TABLE IF NOT EXISTS ua116_spec_fact (
    revision_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    label_ru TEXT NOT NULL,
    display_value TEXT NOT NULL,
    category TEXT NOT NULL,
    unit TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_count INTEGER NOT NULL,
    visible INTEGER NOT NULL,
    manual INTEGER NOT NULL,
    source_domains_json TEXT NOT NULL,
    PRIMARY KEY(revision_id, field_key),
    FOREIGN KEY(revision_id) REFERENCES ua116_spec_revision(revision_id)
);

CREATE TABLE IF NOT EXISTS ua116_worker_heartbeat (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    worker_instance_id TEXT NOT NULL,
    worker_started_at TEXT NOT NULL,
    last_cycle_at TEXT NOT NULL,
    last_success_at TEXT NOT NULL,
    last_cycle_error TEXT NOT NULL,
    queue_depth INTEGER NOT NULL
);

CREATE TRIGGER IF NOT EXISTS ua116_spec_revision_no_delete
BEFORE DELETE ON ua116_spec_revision
BEGIN
    SELECT RAISE(ABORT, 'UA116_SPEC_REVISION_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS ua116_spec_revision_content_immutable
BEFORE UPDATE ON ua116_spec_revision
WHEN NEW.revision_id IS NOT OLD.revision_id
  OR NEW.car_uid IS NOT OLD.car_uid
  OR NEW.vin_sha256 IS NOT OLD.vin_sha256
  OR NEW.policy_version IS NOT OLD.policy_version
  OR NEW.visible_count IS NOT OLD.visible_count
  OR NEW.digest IS NOT OLD.digest
  OR NEW.created_at IS NOT OLD.created_at
  OR NEW.reject_code IS NOT OLD.reject_code
BEGIN
    SELECT RAISE(ABORT, 'UA116_SPEC_REVISION_CONTENT_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS ua116_spec_revision_transition_guard
BEFORE UPDATE ON ua116_spec_revision
WHEN NOT (
       (NEW.status = OLD.status AND NEW.activated_at IS OLD.activated_at)
    OR (OLD.status = 'CANDIDATE' AND NEW.status = 'ACTIVE'
        AND OLD.activated_at IS NULL AND NEW.activated_at IS NOT NULL)
    OR (OLD.status = 'ACTIVE' AND NEW.status = 'ARCHIVED'
        AND NEW.activated_at IS OLD.activated_at)
)
BEGIN
    SELECT RAISE(ABORT, 'UA116_SPEC_REVISION_TRANSITION_INVALID');
END;

CREATE TRIGGER IF NOT EXISTS ua116_spec_fact_candidate_only
BEFORE INSERT ON ua116_spec_fact
WHEN COALESCE((SELECT status FROM ua116_spec_revision
               WHERE revision_id=NEW.revision_id), '') != 'CANDIDATE'
BEGIN
    SELECT RAISE(ABORT, 'UA116_SPEC_FACT_PARENT_NOT_CANDIDATE');
END;

CREATE TRIGGER IF NOT EXISTS ua116_spec_fact_no_update
BEFORE UPDATE ON ua116_spec_fact
BEGIN
    SELECT RAISE(ABORT, 'UA116_SPEC_FACT_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS ua116_spec_fact_no_delete
BEFORE DELETE ON ua116_spec_fact
BEGIN
    SELECT RAISE(ABORT, 'UA116_SPEC_FACT_IMMUTABLE');
END;
"""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=15.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=15000")
    return con


def initialize(path: str | Path) -> None:
    with connect(path) as con:
        con.executescript(SCHEMA)


def _load_revision(con: sqlite3.Connection, row: sqlite3.Row) -> SpecRevision:
    text_revision_fields = (
        "revision_id",
        "car_uid",
        "vin_sha256",
        "policy_version",
        "status",
        "digest",
        "created_at",
        "reject_code",
    )
    if any(type(row[name]) is not str for name in text_revision_fields):
        raise RecoveryGuardError("SPEC_REVISION_STORAGE_TYPE_INVALID")
    if type(row["visible_count"]) is not int or int(row["visible_count"]) < 0:
        raise RecoveryGuardError(
            "SPEC_VISIBLE_COUNT_INVALID", str(row["revision_id"])
        )
    if row["activated_at"] is not None and type(row["activated_at"]) is not str:
        raise RecoveryGuardError(
            "SPEC_ACTIVATED_AT_TYPE_INVALID", str(row["revision_id"])
        )
    facts_list: list[SpecFact] = []
    for item in con.execute(
        "SELECT * FROM ua116_spec_fact WHERE revision_id=? ORDER BY field_key",
        (row["revision_id"],),
    ):
        for name in (
            "revision_id",
            "field_key",
            "label_ru",
            "display_value",
            "category",
            "unit",
            "source_domains_json",
        ):
            if type(item[name]) is not str:
                raise RecoveryGuardError(
                    "SPEC_FACT_STORAGE_TYPE_INVALID", str(row["revision_id"])
                )
        if type(item["evidence_count"]) is not int or int(item["evidence_count"]) < 0:
            raise RecoveryGuardError(
                "SPEC_FACT_EVIDENCE_INVALID", str(item["field_key"])
            )
        if type(item["visible"]) is not int or item["visible"] not in {0, 1}:
            raise RecoveryGuardError(
                "SPEC_FACT_BOOLEAN_INVALID", str(item["field_key"])
            )
        if type(item["manual"]) is not int or item["manual"] not in {0, 1}:
            raise RecoveryGuardError(
                "SPEC_FACT_BOOLEAN_INVALID", str(item["field_key"])
            )
        if type(item["confidence"]) not in {int, float} or not math.isfinite(
            float(item["confidence"])
        ):
            raise RecoveryGuardError(
                "SPEC_FACT_CONFIDENCE_INVALID", str(item["field_key"])
            )
        try:
            domains = json.loads(item["source_domains_json"])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RecoveryGuardError(
                "SPEC_FACT_SOURCE_JSON_INVALID", str(row["revision_id"])
            ) from exc
        if not isinstance(domains, list) or any(
            not isinstance(value, str) for value in domains
        ):
            raise RecoveryGuardError(
                "SPEC_FACT_SOURCE_JSON_INVALID", str(row["revision_id"])
            )
        facts_list.append(
            SpecFact(
                field_key=str(item["field_key"]),
                label_ru=str(item["label_ru"]),
                display_value=str(item["display_value"]),
                category=str(item["category"]),
                unit=str(item["unit"]),
                confidence=float(item["confidence"]),
                evidence_count=int(item["evidence_count"]),
                visible=bool(item["visible"]),
                manual=bool(item["manual"]),
                source_domains=tuple(domains),
            )
        )
    revision = SpecRevision(
        uid=str(row["car_uid"]),
        vin_sha256=str(row["vin_sha256"]),
        policy_version=str(row["policy_version"]),
        revision_id=str(row["revision_id"]),
        status=str(row["status"]),
        facts=tuple(facts_list),
        digest=str(row["digest"]),
        declared_visible_count=int(row["visible_count"]),
    )
    assert_spec_revision_integrity(
        revision, expected_visible_count=int(row["visible_count"])
    )
    return revision


def get_active(path: str | Path, uid: str) -> SpecRevision | None:
    uid = canonical_uid(uid)
    with connect(path) as con:
        row = con.execute(
            "SELECT * FROM ua116_spec_revision WHERE car_uid=? AND status='ACTIVE'",
            (uid,),
        ).fetchone()
        return _load_revision(con, row) if row else None


def stage_and_activate(
    path: str | Path,
    *,
    uid: str,
    vin: str,
    policy_version: str,
    revision_id: str,
    rows: Iterable[SpecFact | Mapping[str, Any]],
    allow_manual_facts: bool = False,
    fault: str = "",
) -> dict[str, Any]:
    """Validate in memory, then insert/activate in one transaction.

    Repeating enrichment for the same VIN is a logical no-op.  The already
    ACTIVE revision is returned unchanged even if new source output differs.
    """

    candidate = build_candidate_revision(
        uid,
        vin,
        policy_version,
        rows,
        revision_id=revision_id,
        allow_manual_facts=allow_manual_facts,
    )
    initialize(path)
    con = connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        current_row = con.execute(
            "SELECT * FROM ua116_spec_revision WHERE car_uid=? AND status='ACTIVE'",
            (candidate.uid,),
        ).fetchone()
        current = _load_revision(con, current_row) if current_row else None
        if current_row and str(current_row["vin_sha256"]) == candidate.vin_sha256:
            assert current is not None
            con.commit()
            return {
                "status": "UNCHANGED",
                "active_revision_id": current.revision_id,
                "active_digest": current.digest,
                "visible_count": current.visible_count,
                "archived_revision_id": "",
            }

        now = utc_now()
        con.execute(
            "INSERT INTO ua116_spec_revision "
            "(revision_id,car_uid,vin_sha256,policy_version,status,visible_count,digest,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                candidate.revision_id,
                candidate.uid,
                candidate.vin_sha256,
                candidate.policy_version,
                "CANDIDATE",
                candidate.visible_count,
                candidate.digest,
                now,
            ),
        )
        con.executemany(
            "INSERT INTO ua116_spec_fact "
            "(revision_id,field_key,label_ru,display_value,category,unit,confidence,evidence_count,visible,manual,source_domains_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    candidate.revision_id,
                    fact.field_key,
                    fact.label_ru,
                    fact.display_value,
                    fact.category,
                    fact.unit,
                    fact.confidence,
                    fact.evidence_count,
                    int(fact.visible),
                    int(fact.manual),
                    json.dumps(fact.source_domains, ensure_ascii=False),
                )
                for fact in candidate.facts
            ],
        )
        persisted_row = con.execute(
            "SELECT * FROM ua116_spec_revision WHERE revision_id=?",
            (candidate.revision_id,),
        ).fetchone()
        if persisted_row is None:
            raise RecoveryGuardError("SPEC_CANDIDATE_PERSIST_FAILED")
        persisted_candidate = _load_revision(con, persisted_row)
        if persisted_candidate.digest != candidate.digest:
            raise RecoveryGuardError("SPEC_CANDIDATE_PERSIST_MISMATCH")
        if fault == "after_candidate":
            raise RuntimeError("INJECTED_AFTER_CANDIDATE")

        archived_id = ""
        if current_row:
            archived_id = str(current_row["revision_id"])
            changed = con.execute(
                "UPDATE ua116_spec_revision SET status='ARCHIVED' "
                "WHERE revision_id=? AND status='ACTIVE' AND digest=?",
                (archived_id, current_row["digest"]),
            )
            if changed.rowcount != 1:
                raise RecoveryGuardError("SPEC_ACTIVE_CAS_CONFLICT")
        activated = con.execute(
            "UPDATE ua116_spec_revision SET status='ACTIVE', activated_at=? "
            "WHERE revision_id=? AND status='CANDIDATE' AND visible_count>=?",
            (now, candidate.revision_id, PUBLIC_MIN_VISIBLE_SPEC_ROWS),
        )
        if activated.rowcount != 1:
            raise RecoveryGuardError("SPEC_ACTIVATION_FAILED")
        if fault == "after_activation":
            raise RuntimeError("INJECTED_AFTER_ACTIVATION")
        con.commit()
        return {
            "status": "ACTIVATED",
            "active_revision_id": candidate.revision_id,
            "active_digest": candidate.digest,
            "visible_count": candidate.visible_count,
            "archived_revision_id": archived_id,
        }
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def record_rejected_candidate(
    path: str | Path,
    *,
    uid: str,
    vin: str,
    policy_version: str,
    revision_id: str,
    visible_count: int,
    reject_code: str,
) -> None:
    """Record failure without touching the ACTIVE revision or its facts."""

    initialize(path)
    with connect(path) as con:
        con.execute(
            "INSERT INTO ua116_spec_revision "
            "(revision_id,car_uid,vin_sha256,policy_version,status,visible_count,digest,created_at,reject_code) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(revision_id),
                canonical_uid(uid),
                vin_sha256(vin),
                str(policy_version),
                "REJECTED",
                int(visible_count),
                "",
                utc_now(),
                str(reject_code),
            ),
        )


def update_heartbeat(
    path: str | Path,
    *,
    worker_instance_id: str,
    worker_started_at: str,
    last_cycle_at: str,
    last_success_at: str,
    last_cycle_error: str,
    queue_depth: int,
) -> None:
    initialize(path)
    with connect(path) as con:
        con.execute(
            "INSERT INTO ua116_worker_heartbeat "
            "(singleton,worker_instance_id,worker_started_at,last_cycle_at,last_success_at,last_cycle_error,queue_depth) "
            "VALUES (1,?,?,?,?,?,?) "
            "ON CONFLICT(singleton) DO UPDATE SET "
            "worker_instance_id=excluded.worker_instance_id,"
            "worker_started_at=excluded.worker_started_at,"
            "last_cycle_at=excluded.last_cycle_at,"
            "last_success_at=excluded.last_success_at,"
            "last_cycle_error=excluded.last_cycle_error,"
            "queue_depth=excluded.queue_depth",
            (
                str(worker_instance_id),
                str(worker_started_at),
                str(last_cycle_at),
                str(last_success_at),
                str(last_cycle_error),
                int(queue_depth),
            ),
        )


def backup_sqlite(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Create a consistent SQLite backup, including WAL state."""

    source_path, destination_path = Path(source), Path(destination)
    if destination_path.exists() or destination_path.is_symlink():
        raise RecoveryGuardError("BACKUP_DESTINATION_EXISTS", str(destination_path))
    if not source_path.is_file() or source_path.is_symlink():
        raise RecoveryGuardError("BACKUP_SOURCE_INVALID", str(source_path))
    source_con = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True)
    destination_con = sqlite3.connect(str(destination_path))
    try:
        source_con.backup(destination_con)
        quick = str(destination_con.execute("PRAGMA quick_check").fetchone()[0])
        if quick != "ok":
            raise RecoveryGuardError("BACKUP_QUICK_CHECK_FAILED", quick)
        destination_con.commit()
        return {
            "status": "PASS",
            "source": str(source_path),
            "destination": str(destination_path),
            "quick_check": quick,
            "bytes": destination_path.stat().st_size,
        }
    finally:
        destination_con.close()
        source_con.close()
