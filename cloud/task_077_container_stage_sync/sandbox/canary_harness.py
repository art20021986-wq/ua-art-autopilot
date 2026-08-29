#!/usr/bin/env python3
"""
Sandbox/canary harness for TASK 077.

Builds an isolated, synthetic, in-memory-or-tempfile SQLite CRM copy. Never
touches the real crm.db. Applies the extended ETA transaction and stage-sync
patch logic, then runs the required deterministic canary scenarios.

Run directly: `python3 canary_harness.py`
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "patcher"))

from eta_transaction_controller import (  # noqa: E402
    apply_stage_sync_transaction,
    migrate_legacy_sea_transit,
    StageSyncError,
)
from postcheck import readback_car  # noqa: E402


def build_synthetic_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE cars (id TEXT PRIMARY KEY, status TEXT, days_to_kyiv INTEGER,"
        " eta_manual TEXT, updated_at TEXT, published INTEGER, vin TEXT, price TEXT,"
        " description TEXT, photo_hash TEXT, video_hash TEXT, diag_hash TEXT)"
    )
    rows = [
        ("UA-0012", "sea_transit", None, None, None, 0, "VIN0012", "12000", "desc12",
         "phash12", "vhash12", None),
        ("UA-0009", "sea_loaded", 12, "2026-09-10", "2026-08-27T00:00:00", 1, "VIN0009",
         "9000", "desc9", "phash9", "vhash9", "dhash9"),
        ("UA-0020", "georgia", None, None, None, 1, "VIN0020", "20000", "desc20",
         "phash20", "vhash20", "dhash20"),
        ("UA-0021", "kyiv", None, None, None, 1, "VIN0021", "21000", "desc21",
         "phash21", "vhash21", "dhash21"),
        ("UA-0022", "sold", None, None, None, 1, "VIN0022", "22000", "desc22",
         "phash22", "vhash22", "dhash22"),
        ("UA-0023", "sold_transit", None, None, None, 1, "VIN0023", "23000", "desc23",
         "phash23", "vhash23", "dhash23"),
        ("UA-0999", "sea_transit", None, None, None, 0, "VIN0999", "9990", "desc999",
         "phash999", "vhash999", None),  # synthetic future card, no diagnostics yet
    ]
    conn.executemany(
        "INSERT INTO cars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
    )
    conn.commit()
    return conn


def snapshot_unrelated(conn) -> dict:
    ids = ["UA-0020", "UA-0021", "UA-0022", "UA-0023"]
    snap = {}
    for cid in ids:
        row = conn.execute(
            "SELECT vin, price, description, photo_hash, video_hash, diag_hash, status,"
            " published FROM cars WHERE id=?",
            (cid,),
        ).fetchone()
        snap[cid] = hashlib.sha256(str(row).encode()).hexdigest()
    return snap


def always_true(_car_id):
    return True


def placeholder_or_diag(car_id):
    """Simulates: creates canonical placeholder page when diagnostics are
    missing, always returns True (staging placeholder is not a failure)."""
    return True


def readback_adapter(conn, car_id):
    return readback_car(conn, car_id)


def run_scenario_ua0012(conn) -> bool:
    result = apply_stage_sync_transaction(
        conn,
        "UA-0012",
        days_to_kyiv=30,
        today=dt.date(2026, 8, 29),
        rebuild_primary_fn=always_true,
        rebuild_diag_or_placeholder_fn=placeholder_or_diag,
        rebuild_catalog_fns=[always_true, always_true],
        readback_fn=readback_adapter,
        canary_video_fn=always_true,
        canary_site_fn=always_true,
    )
    rb = readback_car(conn, "UA-0012")
    ok = (
        result.ok
        and rb["status"] == "sea_loaded"
        and rb["days_to_kyiv"] == 30
        and rb["eta_manual"] == "2026-09-28"
        and rb["published"] == 1
    )
    print(f"SCENARIO UA-0012 -> ok={ok} message={result.message} readback={rb}")
    return ok


def run_scenario_ua0009(conn) -> bool:
    before = readback_car(conn, "UA-0009")
    result = apply_stage_sync_transaction(
        conn,
        "UA-0009",
        days_to_kyiv=12,
        today=dt.date(2026, 8, 27),
        rebuild_primary_fn=always_true,
        rebuild_diag_or_placeholder_fn=placeholder_or_diag,
        rebuild_catalog_fns=[always_true, always_true],
        readback_fn=readback_adapter,
        canary_video_fn=always_true,
        canary_site_fn=always_true,
    )
    after = readback_car(conn, "UA-0009")
    ok = result.ok and after["status"] == "sea_loaded" and after["eta_manual"] == before["eta_manual"]
    print(f"SCENARIO UA-0009 -> ok={ok} message={result.message}")
    return ok


def run_scenario_future_card(conn) -> bool:
    result = apply_stage_sync_transaction(
        conn,
        "UA-0999",
        days_to_kyiv=5,
        today=dt.date(2026, 8, 29),
        rebuild_primary_fn=always_true,
        rebuild_diag_or_placeholder_fn=placeholder_or_diag,
        rebuild_catalog_fns=[always_true, always_true],
        readback_fn=readback_adapter,
        canary_video_fn=always_true,
        canary_site_fn=always_true,
    )
    rb = readback_car(conn, "UA-0999")
    ok = result.ok and rb["status"] == "sea_loaded"
    print(f"SCENARIO UA-0999(future,no-diag) -> ok={ok} message={result.message}")
    return ok


def run_failure_injection(conn) -> bool:
    def failing_publisher(_cid):
        return False

    before = readback_car(conn, "UA-0012")
    result = apply_stage_sync_transaction(
        conn,
        "UA-0012",
        days_to_kyiv=10,
        today=dt.date(2026, 8, 29),
        rebuild_primary_fn=failing_publisher,
        rebuild_diag_or_placeholder_fn=placeholder_or_diag,
        rebuild_catalog_fns=[always_true, always_true],
        readback_fn=readback_adapter,
        canary_video_fn=always_true,
        canary_site_fn=always_true,
    )
    after = readback_car(conn, "UA-0012")
    ok = (not result.ok) and result.rolled_back and after["status"] == before["status"] \
        and after["published"] == before["published"]
    print(f"SCENARIO failure-injection(publisher FAIL) -> ok={ok} message={result.message}")
    return ok


def run_legacy_migration_plan(conn) -> list:
    cur = conn.execute("SELECT id FROM cars WHERE status='sea_transit'")
    legacy_ids = [r[0] for r in cur.fetchall()]
    print(f"LEGACY_MIGRATION_PLAN (no live write): {legacy_ids}")
    return legacy_ids


def main() -> int:
    all_pass = True
    for run_idx in (1, 2):
        conn = build_synthetic_db()
        before_snapshot = snapshot_unrelated(conn)
        legacy_plan = run_legacy_migration_plan(conn)

        r1 = run_scenario_ua0012(conn)
        r2 = run_scenario_ua0009(conn)
        r3 = run_scenario_future_card(conn)
        r4 = run_failure_injection(conn)

        after_snapshot = snapshot_unrelated(conn)
        unrelated_ok = before_snapshot == after_snapshot
        print(f"RUN {run_idx}: unrelated cards byte/hash unchanged = {unrelated_ok}")

        run_ok = all([r1, r2, r3, r4, unrelated_ok])
        print(f"RUN {run_idx} RESULT: {'PASS' if run_ok else 'FAIL'}")
        all_pass = all_pass and run_ok
        conn.close()

    print(f"FINAL SANDBOX RESULT: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
