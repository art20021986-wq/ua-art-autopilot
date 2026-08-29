#!/usr/bin/env python3
"""
Extended single ETA transaction for TASK 077.

This EXTENDS the TASK 076 ETA writer contract; it does not create a second
competing writer. If the real active writer function differs in name/location
from the placeholder below, the controller must adapt call sites during Gate B
only, keeping this same transaction body as the single source of truth.

Never executed against production from this environment. SANDBOX-only usage
is demonstrated in sandbox/canary_harness.py.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

CANONICAL_FERRY_STATUS = "sea_loaded"
LEGACY_FERRY_STATUS = "sea_transit"
SOLD_TRANSIT_STATUS = "sold_transit"  # never touched by this transaction
BACKWARD_PROTECTED_STAGES = {"georgia", "kyiv", "sold", "sold_transit", "terminal", "archive"}
MAX_DAYS = 400


class StageSyncError(Exception):
    pass


@dataclass
class TransactionResult:
    ok: bool
    message: str
    car_id: str
    rolled_back: bool = False


def _validate_days(n: int) -> None:
    if not isinstance(n, int):
        raise StageSyncError("invalid days value: not an integer")
    if n < 0 or n > MAX_DAYS:
        raise StageSyncError(f"invalid days value: {n} out of range [0,{MAX_DAYS}]")


def apply_stage_sync_transaction(
    conn: sqlite3.Connection,
    car_id: str,
    days_to_kyiv: int,
    today: dt.date,
    rebuild_primary_fn,
    rebuild_diag_or_placeholder_fn,
    rebuild_catalog_fns,  # list of two callables
    readback_fn,
    canary_video_fn,
    canary_site_fn,
) -> TransactionResult:
    """
    One bounded logical transaction. On any failure: full rollback, preimage
    restored, no success message ever emitted for this call.
    """
    _validate_days(days_to_kyiv)

    cur = conn.execute("SELECT status, published FROM cars WHERE id=?", (car_id,))
    row = cur.fetchone()
    if row is None:
        return TransactionResult(False, f"car not found: {car_id}", car_id)
    preimage_status, preimage_published = row

    if preimage_status in BACKWARD_PROTECTED_STAGES:
        return TransactionResult(
            False,
            f"refused: cannot move protected stage '{preimage_status}' backward via ETA edit",
            car_id,
        )

    new_status = CANONICAL_FERRY_STATUS
    eta_manual = (today + dt.timedelta(days=days_to_kyiv)).isoformat()
    updated_at = dt.datetime.utcnow().isoformat()

    savepoint = f"sp_{car_id.replace('-', '_')}"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        conn.execute(
            "UPDATE cars SET status=?, days_to_kyiv=?, eta_manual=?, updated_at=?, published=0 "
            "WHERE id=?",
            (new_status, days_to_kyiv, eta_manual, updated_at, car_id),
        )

        diag_ok = rebuild_diag_or_placeholder_fn(car_id)
        if not diag_ok:
            raise StageSyncError("diagnostic/placeholder staging failed")

        primary_ok = rebuild_primary_fn(car_id)
        if not primary_ok:
            raise StageSyncError("primary rebuild failed")

        for fn in rebuild_catalog_fns:
            if not fn(car_id):
                raise StageSyncError("catalog rebuild failed")

        rb = readback_fn(conn, car_id)
        if rb.get("status") != new_status or rb.get("days_to_kyiv") != days_to_kyiv \
                or rb.get("eta_manual") != eta_manual:
            raise StageSyncError("read-back mismatch after write")

        if not canary_video_fn(car_id):
            raise StageSyncError("/video canary failed")
        if not canary_site_fn(car_id):
            raise StageSyncError("/site canary failed")

        conn.execute("UPDATE cars SET published=1 WHERE id=?", (car_id,))
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()
        return TransactionResult(True, "PASS: stage sync verified", car_id)

    except Exception as exc:  # noqa: BLE001 - deliberate broad rollback boundary
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.execute(
            "UPDATE cars SET published=? WHERE id=?", (preimage_published, car_id)
        )
        conn.commit()
        return TransactionResult(False, f"FAIL: {exc}", car_id, rolled_back=True)


def migrate_legacy_sea_transit(conn: sqlite3.Connection, allow: bool = False):
    """Bounded row-level legacy migration. Disabled by default; requires an
    explicit production approval flag to ever run for real, and is exercised
    only in sandbox here."""
    if not allow:
        raise StageSyncError("legacy migration is disabled: requires ALLOW_LEGACY_MIGRATION=True"
                              " and separate production approval")
    cur = conn.execute("SELECT id FROM cars WHERE status=?", (LEGACY_FERRY_STATUS,))
    ids = [r[0] for r in cur.fetchall()]
    for cid in ids:
        conn.execute(f"SAVEPOINT sp_mig_{cid.replace('-', '_')}")
        try:
            conn.execute("UPDATE cars SET status=? WHERE id=?", (CANONICAL_FERRY_STATUS, cid))
            conn.execute(f"RELEASE SAVEPOINT sp_mig_{cid.replace('-', '_')}")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT sp_mig_{cid.replace('-', '_')}")
            conn.execute(f"RELEASE SAVEPOINT sp_mig_{cid.replace('-', '_')}")
            raise
    conn.commit()
    return ids
