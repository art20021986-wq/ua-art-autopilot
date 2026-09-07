#!/usr/bin/env python3
"""Transactional empty-only writer for the CRM primary specification.

The existing TASK111 additional-spec service must remain unable to write
primary CRM fields.  This narrowly scoped adapter is the only proposed write
path.  It is safe for Gate B copies by default; a future Production integration
must explicitly pass ``allow_production=True`` after the separate owner gate.
"""
from __future__ import annotations

import datetime as dt
import math
import json
import os
import sqlite3
import stat
import re
from pathlib import Path
from typing import Any, Mapping

from recovery_core import (
    ALL_PRIMARY_FIELDS,
    BaseFillPlan,
    RecoveryGuardError,
    VEHICLE_PRIMARY_FIELDS,
    canonical_uid,
    is_blank,
    normalize_vin,
    plan_base_fill,
    resolved_under,
    stable_digest,
    vin_sha256,
)


AUDIT_COLUMNS = {
    "actor_id",
    "action",
    "entity_type",
    "entity_id",
    "field",
    "old_value",
    "new_value",
    "created_at",
}

ALLOWED_SOURCE_KINDS = frozenset(
    {"vin_decoder", "auction_record", "same_vin_crm", "operator"}
)
VEHICLE_SOURCE_KINDS = frozenset(
    {"auction_record", "same_vin_crm", "operator"}
)
MINIMUM_CONFIDENCE = 0.90


def _plain_row(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if isinstance(value, bytes):
            value = {"bytes_sha256": __import__("hashlib").sha256(value).hexdigest()}
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            value = str(value)
        result[str(key)] = value
    return result


def row_digest(row: sqlite3.Row | Mapping[str, Any]) -> str:
    return stable_digest(_plain_row(row))


def _quoted(field: str) -> str:
    if field not in ALL_PRIMARY_FIELDS:
        raise RecoveryGuardError("BASE_FIELD_NOT_ALLOWLISTED", field)
    return '"' + field + '"'


def _single_link_identity(
    path: Path, expected: tuple[int, int] | None = None
) -> tuple[int, int]:
    """Reject aliases to a live DB and replacement of the checked file.

    Resolving a path prevents a symlink escape but cannot reveal a hard link.
    A preview database must therefore be a regular, single-link file for the
    complete transaction.  ``(st_dev, st_ino)`` also binds the SQLite handle
    to the file that was checked before it was opened.
    """

    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise RecoveryGuardError("CRM_DB_NOT_FOUND", str(path)) from exc
    if not stat.S_ISREG(info.st_mode):
        raise RecoveryGuardError("CRM_DB_NOT_REGULAR", str(path))
    if int(info.st_nlink) != 1:
        raise RecoveryGuardError("CRM_DB_HARDLINK_FORBIDDEN", str(path))
    identity = (int(info.st_dev), int(info.st_ino))
    if expected is not None and identity != expected:
        raise RecoveryGuardError("CRM_DB_PATH_REPLACED", str(path))
    return identity


def _validated_plan_snapshot(
    plan: BaseFillPlan,
    *,
    before: Mapping[str, Any],
    expected_vin: str,
    expected_row_digest: str,
    actor_id: int | None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], str]:
    """Re-run the candidate policy at the write boundary.

    ``BaseFillPlan`` contains mappings, so the frozen dataclass alone does not
    make a caller-supplied plan immutable.  Copy and validate every value,
    provenance field and VIN binding before constructing any UPDATE.
    """

    if str(plan.before_digest) != str(expected_row_digest):
        raise RecoveryGuardError("PLAN_BEFORE_DIGEST_MISMATCH")

    raw_writes = dict(plan.writes)
    raw_provenance = dict(plan.provenance)
    if set(raw_writes) != set(raw_provenance):
        raise RecoveryGuardError("BASE_PLAN_PROVENANCE_FIELDS_MISMATCH")

    expected_vin_digest = vin_sha256(expected_vin)
    writes: dict[str, str] = {}
    provenance: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    for field in sorted(raw_writes):
        if field not in ALL_PRIMARY_FIELDS:
            raise RecoveryGuardError("BASE_FIELD_NOT_ALLOWLISTED", str(field))
        value = raw_writes[field]
        if not isinstance(value, str) or is_blank(value):
            raise RecoveryGuardError("BASE_PLAN_VALUE_INVALID", str(field))
        if len(value) > 200 or value != value.strip() or re.search(r"[\x00-\x1f\x7f<>]", value):
            raise RecoveryGuardError("BASE_PLAN_VALUE_INVALID", str(field))
        raw_meta = raw_provenance[field]
        if not isinstance(raw_meta, Mapping):
            raise RecoveryGuardError("BASE_PLAN_PROVENANCE_INVALID", str(field))
        if set(raw_meta) != {"source_kind", "source", "confidence", "vin_sha256"}:
            raise RecoveryGuardError("BASE_PLAN_PROVENANCE_INVALID", str(field))
        source_kind = str(raw_meta.get("source_kind") or "").strip()
        source = str(raw_meta.get("source") or "").strip()
        try:
            confidence = float(raw_meta.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise RecoveryGuardError(
                "BASE_PLAN_CONFIDENCE_INVALID", str(field)
            ) from exc
        provenance_vin = str(raw_meta.get("vin_sha256") or "")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            raise RecoveryGuardError("BASE_PLAN_SOURCE_KIND_INVALID", str(field))
        if source_kind == "vin_decoder" and source != "vpic.nhtsa.dot.gov":
            raise RecoveryGuardError("BASE_PLAN_SOURCE_INVALID", str(field))
        if source_kind == "same_vin_crm" and source != "crm:same-vin":
            raise RecoveryGuardError("BASE_PLAN_SOURCE_INVALID", str(field))
        if source_kind == "auction_record" and not re.fullmatch(
            r"auction:[A-Za-z0-9._:-]{1,160}", source
        ):
            raise RecoveryGuardError("BASE_PLAN_SOURCE_INVALID", str(field))
        if source_kind == "operator":
            if actor_id is None or source != "operator:" + str(int(actor_id)):
                raise RecoveryGuardError("BASE_PLAN_OPERATOR_AUTH_REQUIRED", str(field))
        if field in VEHICLE_PRIMARY_FIELDS and source_kind not in VEHICLE_SOURCE_KINDS:
            raise RecoveryGuardError("BASE_PLAN_VEHICLE_SOURCE_INVALID", str(field))
        if not source or len(source) > 512:
            raise RecoveryGuardError("BASE_PLAN_SOURCE_INVALID", str(field))
        if (
            not math.isfinite(confidence)
            or confidence < MINIMUM_CONFIDENCE
            or confidence > 1.0
        ):
            raise RecoveryGuardError("BASE_PLAN_CONFIDENCE_INVALID", str(field))
        if provenance_vin != expected_vin_digest:
            raise RecoveryGuardError("BASE_PLAN_VIN_MISMATCH", str(field))
        writes[field] = value
        provenance[field] = {
            "source_kind": source_kind,
            "source": source,
            "confidence": confidence,
            "vin_sha256": provenance_vin,
        }
        candidates.append({"field": field, "value": value, **provenance[field]})

    # Reapply the same empty-only/source policy to the actual row.  This also
    # prevents a hand-crafted plan from bypassing planner policy.
    replay = plan_base_fill(
        before,
        candidates,
        expected_vin=expected_vin,
        minimum_confidence=MINIMUM_CONFIDENCE,
    )
    if dict(replay.writes) != writes or dict(replay.provenance) != provenance:
        raise RecoveryGuardError("BASE_PLAN_REPLAY_MISMATCH")

    audit_digest = stable_digest(
        {
            "writes": writes,
            "provenance": provenance,
            "preserved": tuple(plan.preserved),
            "rejected": tuple(plan.rejected),
            "before_digest": str(plan.before_digest),
        }
    )
    if audit_digest != plan.audit_digest:
        raise RecoveryGuardError("BASE_PLAN_MUTATED")
    return writes, provenance, audit_digest


def _guarded_cars_digest(
    connection: sqlite3.Connection,
    *,
    card_id: int,
    permitted_fields: frozenset[str],
) -> str:
    """Digest all cars while masking only the intended target cells."""

    rows: list[dict[str, Any]] = []
    for row in connection.execute("SELECT * FROM cars ORDER BY id"):
        item = _plain_row(row)
        if int(item.get("id")) == int(card_id):
            for field in permitted_fields:
                item.pop(field, None)
        rows.append(item)
    return stable_digest(rows)


def _audit_action(
    *,
    plan_audit_digest: str,
    expected_row_digest: str,
    provenance: Mapping[str, Any],
    value: str,
) -> str:
    """Carry provenance in the only extensible legacy audit column."""

    metadata = {
        "before_row_digest": expected_row_digest,
        "plan_audit_digest": plan_audit_digest,
        "provenance": dict(provenance),
        "value_digest": stable_digest(value),
    }
    return "vin_base_spec_empty_only " + json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def apply_fill_plan(
    db_path: str | Path,
    *,
    card_id: int,
    uid: str,
    expected_vin: str,
    plan: BaseFillPlan,
    actor_id: int | None,
    expected_row_digest: str,
    preview_root: str | Path | None = None,
    allow_production: bool = False,
    fault: str = "",
) -> dict[str, Any]:
    """Apply all still-empty fields and audit rows in one SQLite transaction."""

    path = Path(db_path)
    if not allow_production:
        if preview_root is None:
            raise RecoveryGuardError("PREVIEW_ROOT_REQUIRED")
        path = resolved_under(preview_root, path)
    file_identity = _single_link_identity(path)
    normalized_uid = canonical_uid(uid)
    normalized_vin = normalize_vin(expected_vin)

    invalid = sorted(set(plan.writes) - ALL_PRIMARY_FIELDS)
    if invalid:
        raise RecoveryGuardError("BASE_FIELD_NOT_ALLOWLISTED", ",".join(invalid))

    connection = sqlite3.connect(str(path), timeout=15.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("BEGIN IMMEDIATE")
        _single_link_identity(path, file_identity)
        car_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")
        }
        if not {"id", "auto_number", "vin"}.issubset(car_columns):
            raise RecoveryGuardError("CRM_SCHEMA_MISMATCH")
        unknown = sorted(set(plan.writes) - car_columns)
        if unknown:
            raise RecoveryGuardError("CRM_FIELD_MISSING", ",".join(unknown))
        audit_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(audit)")
        }
        if not AUDIT_COLUMNS.issubset(audit_columns):
            raise RecoveryGuardError("CRM_AUDIT_SCHEMA_MISMATCH")

        before = connection.execute(
            "SELECT * FROM cars WHERE id=?", (int(card_id),)
        ).fetchone()
        if before is None:
            raise RecoveryGuardError("CARD_NOT_FOUND", str(card_id))
        if canonical_uid(before["auto_number"]) != normalized_uid:
            raise RecoveryGuardError("CARD_UID_CHANGED")
        if normalize_vin(before["vin"]) != normalized_vin:
            raise RecoveryGuardError("CARD_VIN_CHANGED")
        actual_before_digest = row_digest(before)
        if actual_before_digest != expected_row_digest:
            raise RecoveryGuardError("STALE_CARD_REVISION")

        writes, provenance, plan_audit_digest = _validated_plan_snapshot(
            plan,
            before=_plain_row(before),
            expected_vin=normalized_vin,
            expected_row_digest=expected_row_digest,
            actor_id=actor_id,
        )

        skipped_nonempty = tuple(
            sorted(field for field in plan.writes if field not in writes)
        )
        guarded_before = _guarded_cars_digest(
            connection,
            card_id=int(card_id),
            permitted_fields=frozenset(writes),
        )
        change_count_before = connection.total_changes
        if writes:
            fields = sorted(writes)
            setters = ", ".join(f"{_quoted(field)}=?" for field in fields)
            empty_cas = " AND ".join(
                f"TRIM(COALESCE(CAST({_quoted(field)} AS TEXT),''))=''"
                for field in fields
            )
            sql = (
                f"UPDATE cars SET {setters} WHERE id=? AND auto_number=? "
                "AND UPPER(REPLACE(REPLACE(vin,' ',''),'-',''))=? AND "
                + empty_cas
            )
            cursor = connection.execute(
                sql,
                tuple(writes[field] for field in fields)
                + (int(card_id), normalized_uid, normalized_vin),
            )
            if cursor.rowcount != 1:
                raise RecoveryGuardError("BASE_SPEC_CAS_CONFLICT")
            if fault == "after_update":
                raise RuntimeError("INJECTED_AFTER_UPDATE")

            timestamp = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
            for field in fields:
                audit_cursor = connection.execute(
                    "INSERT INTO audit "
                    "(actor_id,action,entity_type,entity_id,field,old_value,new_value,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        actor_id,
                        _audit_action(
                            plan_audit_digest=plan_audit_digest,
                            expected_row_digest=expected_row_digest,
                            provenance=provenance[field],
                            value=writes[field],
                        ),
                        "cars",
                        int(card_id),
                        field,
                        before[field],
                        writes[field],
                        timestamp,
                    ),
                )
                if audit_cursor.rowcount != 1:
                    raise RecoveryGuardError("BASE_SPEC_AUDIT_WRITE_FAILED", field)
            if fault == "after_audit":
                raise RuntimeError("INJECTED_AFTER_AUDIT")

        after = connection.execute(
            "SELECT * FROM cars WHERE id=?", (int(card_id),)
        ).fetchone()
        for field, expected in writes.items():
            if str(after[field]) != str(expected):
                raise RecoveryGuardError("BASE_SPEC_READBACK_MISMATCH", field)
        guarded_after = _guarded_cars_digest(
            connection,
            card_id=int(card_id),
            permitted_fields=frozenset(writes),
        )
        expected_change_count = (1 + len(writes)) if writes else 0
        observed_change_count = connection.total_changes - change_count_before
        if guarded_after != guarded_before or observed_change_count != expected_change_count:
            raise RecoveryGuardError(
                "BASE_SPEC_TRIGGER_SIDE_EFFECT",
                f"changes={observed_change_count}/{expected_change_count}",
            )
        if plan.audit_digest != plan_audit_digest:
            raise RecoveryGuardError("BASE_PLAN_MUTATED")
        _single_link_identity(path, file_identity)
        connection.commit()
        receipt = {
            "status": "APPLIED" if writes else "NOOP",
            "card_id": int(card_id),
            "uid": normalized_uid,
            "vin_sha256": vin_sha256(normalized_vin),
            "written_fields": sorted(writes),
            "skipped_nonempty": list(skipped_nonempty),
            "before_row_digest": row_digest(before),
            "after_row_digest": row_digest(after),
            "plan_audit_digest": plan_audit_digest,
        }
        receipt["receipt_digest"] = stable_digest(receipt)
        return receipt
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        raise
    finally:
        connection.close()


def receipt_json(receipt: Mapping[str, Any]) -> str:
    return json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
