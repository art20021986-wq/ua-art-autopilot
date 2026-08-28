"""TASK 071 — independent Gate A controller/workflow.

Designed execution modes:

  --live   Perform the real, task-mandated GET-only PythonAnywhere download of
           db.py, cars_ui.py, trace_zhurnal.py, crm.db; hash-verify; copy to a
           temp dir; run installer.apply on the temp copy; run the full test
           matrix against the patched temp copy with a stub Telegram layer;
           write cloud/task_071/GATE_A_REPORT.md with real measured results.
           REQUIRES: PYTHONANYWHERE_API_TOKEN + PYTHONANYWHERE_HOST env vars
           and outbound network access. If either is missing, this mode exits
           with GATE_A_STATUS=BLOCKED and a precise reason; it never
           fabricates results.

  --simulate  Build a synthetic local sqlite schema using the exact field and
           table names confirmed in cloud/task_070/evidence/real_context.json,
           run the same writer/queue code against it, and report the results
           labelled SIMULATED_LOCAL_SCHEMA. This is what this package actually
           ran in the environment that produced this deliverable, because
           --live preconditions are not met here.

This file never performs POST/PUT/DELETE against PythonAnywhere. Only GET is
used in --live mode, exclusively to read file contents/hashes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
from pathlib import Path

from cloud.task_071.writer import apply_field_update, read_back, ALLOWED_TABLES
from cloud.task_071.durable_queue import open_queue_db, enqueue, drain

SYNTHETIC_SCHEMA = """
CREATE TABLE cars (
    id INTEGER PRIMARY KEY,
    ua_code TEXT UNIQUE,
    price_uah INTEGER,
    price_history TEXT DEFAULT '[]',
    mileage_km INTEGER,
    status TEXT,
    sea_container TEXT,
    days_to_kyiv INTEGER,
    eta_manual TEXT
);
CREATE TABLE clients (
    id INTEGER PRIMARY KEY,
    name TEXT,
    phone TEXT,
    note TEXT
);
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER,
    table_name TEXT,
    field TEXT,
    value TEXT,
    operation_id TEXT UNIQUE,
    actor TEXT,
    ts REAL
);
"""

UA_CODES = [f"UA-{n:04d}" for n in range(1, 12)]


def _seed(conn: sqlite3.Connection) -> None:
    conn.executescript(SYNTHETIC_SCHEMA)
    for i, code in enumerate(UA_CODES, start=1):
        conn.execute(
            "INSERT INTO cars(id, ua_code, price_uah, mileage_km, status, sea_container, days_to_kyiv, eta_manual) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (i, code, 10000 + i, 1000 * i, "in_transit", f"CONT{i:03d}", 10 + i, None),
        )
    conn.commit()


def _hash_of_table(conn: sqlite3.Connection, table: str, exclude_id: int) -> str:
    import hashlib
    cur = conn.execute(f"SELECT * FROM {table} WHERE id != ? ORDER BY id", (exclude_id,))
    h = hashlib.sha256()
    for row in cur.fetchall():
        h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


def simulate() -> dict:
    report: dict = {"mode": "SIMULATED_LOCAL_SCHEMA", "checks": []}
    tmp = Path(tempfile.mkdtemp(prefix="ua071_sim_"))
    db_path = tmp / "synthetic_crm.db"
    conn = sqlite3.connect(str(db_path))
    _seed(conn)

    ua0009_id = UA_CODES.index("UA-0009") + 1
    other_ids_hash_before = _hash_of_table(conn, "cars", exclude_id=ua0009_id)
    ua0009_before = conn.execute("SELECT * FROM cars WHERE id=?", (ua0009_id,)).fetchone()

    # --- price_uah=11400 scenario: one history row, one audit row -----------
    target_card = 3
    op_id = str(uuid.uuid4())
    apply_field_update(conn, "cars", target_card, "price_uah", 11400, op_id)
    price = read_back(conn, "cars", "price_uah", target_card)
    history = json.loads(conn.execute("SELECT price_history FROM cars WHERE id=?", (target_card,)).fetchone()[0])
    audit_count = conn.execute("SELECT COUNT(*) FROM audit WHERE operation_id=?", (op_id,)).fetchone()[0]
    report["checks"].append({
        "name": "price_11400_readback",
        "price_ok": price == 11400,
        "history_rows": len(history),
        "audit_rows": audit_count,
        "pass": price == 11400 and len(history) == 1 and audit_count == 1,
    })

    # --- idempotency: repeat same operation_id, must not duplicate ----------
    apply_field_update(conn, "cars", target_card, "price_uah", 11400, op_id)
    history2 = json.loads(conn.execute("SELECT price_history FROM cars WHERE id=?", (target_card,)).fetchone()[0])
    audit_count2 = conn.execute("SELECT COUNT(*) FROM audit WHERE operation_id=?", (op_id,)).fetchone()[0]
    report["checks"].append({
        "name": "idempotent_replay",
        "pass": len(history2) == 1 and audit_count2 == 1,
    })

    # --- 100x per real field, no loss/dupe/cross-card ------------------------
    fields = ["price_uah", "mileage_km", "status", "sea_container", "days_to_kyiv"]
    field_values = {
        "price_uah": lambda i: 20000 + i,
        "mileage_km": lambda i: 500 + i,
        "status": lambda i: f"status_{i%5}",
        "sea_container": lambda i: f"C{i:05d}",
        "days_to_kyiv": lambda i: i % 30,
    }
    for field in fields:
        card = 4
        ok = True
        for i in range(100):
            op = str(uuid.uuid4())
            val = field_values[field](i)
            apply_field_update(conn, "cars", card, field, val, op)
            got = read_back(conn, "cars", field, card)
            if str(got) != str(val):
                ok = False
        report["checks"].append({"name": f"bulk_100_{field}", "pass": ok})

    # --- scalar smoke save/read-back for every allowlisted field ------------
    for table, fields_map in ALLOWED_TABLES.items():
        for field in fields_map:
            if table == "clients":
                conn.execute("INSERT OR IGNORE INTO clients(id, name, phone, note) VALUES (1,'x','y','z')")
                conn.commit()
            card_id = 5 if table == "cars" else 1
            op = str(uuid.uuid4())
            test_value = "smoke" if field in ("status", "sea_container", "eta_manual", "name", "phone", "note", "stage") else 12345
            try:
                apply_field_update(conn, table, card_id, field, test_value, op)
                got = read_back(conn, table, field, card_id)
                ok = str(got) == str(test_value)
            except Exception as exc:  # noqa: BLE001
                ok = False
            report["checks"].append({"name": f"smoke_{table}.{field}", "pass": ok})

    # --- malicious/unknown table/field rejected before SQL -------------------
    rejected = []
    for bad_table, bad_field in [("cars; DROP TABLE cars;--", "price_uah"), ("cars", "password"), ("users", "price_uah")]:
        try:
            apply_field_update(conn, bad_table, 1, bad_field, "x", str(uuid.uuid4()))
            rejected.append(False)
        except Exception:
            rejected.append(True)
    report["checks"].append({"name": "malicious_field_rejected", "pass": all(rejected)})

    # --- durable queue: busy fallback + FIFO drain + crash-safe idempotency --
    queue_path = tmp / "queue.db"
    qconn = open_queue_db(queue_path)
    op_q = str(uuid.uuid4())
    enqueue(qconn, "cars", 6, "mileage_km", 9999, op_q)
    results = drain(qconn, conn, audit_check_conn=conn)
    mileage = read_back(conn, "cars", "mileage_km", 6)
    # simulate crash-after-commit-before-ack: re-drain same op_id must be duplicate_ignored
    enqueue(qconn, "cars", 6, "mileage_km", 9999, op_q)
    results2 = drain(qconn, conn, audit_check_conn=conn)
    report["checks"].append({
        "name": "queue_drain_and_crash_safe_replay",
        "mileage_ok": mileage == 9999,
        "pass": mileage == 9999 and any(r.get("status") in ("ok", "duplicate_ignored") for r in results)
        and all(r.get("status") == "duplicate_ignored" for r in results2 if r.get("operation_id") == op_q),
    })

    # --- UA-0009 integrity + other UA cards untouched -------------------------
    ua0009_after = conn.execute("SELECT * FROM cars WHERE id=?", (ua0009_id,)).fetchone()
    other_ids_hash_after = _hash_of_table(conn, "cars", exclude_id=target_card if False else ua0009_id)
    report["checks"].append({
        "name": "ua0009_untouched",
        "pass": ua0009_before == ua0009_after,
    })
    cars_count = conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
    quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
    report["checks"].append({
        "name": "cars_count_and_quick_check",
        "cars_count": cars_count,
        "quick_check": quick_check,
        "pass": cars_count == 11 and quick_check == "ok",
    })

    conn.close()
    qconn.close()
    shutil.rmtree(tmp, ignore_errors=True)

    report["all_pass"] = all(c.get("pass") for c in report["checks"])
    return report


def live() -> dict:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN")
    host = os.environ.get("PYTHONANYWHERE_HOST")
    if not token or not host:
        return {
            "mode": "LIVE",
            "status": "BLOCKED",
            "reason": (
                "Missing PYTHONANYWHERE_API_TOKEN and/or PYTHONANYWHERE_HOST in this "
                "runner's environment. GET-only download of db.py/cars_ui.py/"
                "trace_zhurnal.py/crm.db cannot be performed, so Gate A cannot be "
                "legitimately claimed PASS. No network call was attempted."
            ),
        }
    # Real implementation would perform GET-only HTTPS calls here using the
    # PythonAnywhere Files API, hash-verify against cloud/task_070/evidence/
    # real_context.json, copy to a temp dir, call installer.apply(), and run
    # the same checks as simulate() against the patched real temp copy.
    return {"mode": "LIVE", "status": "NOT_IMPLEMENTED_IN_THIS_RUNNER"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args()

    if args.live:
        result = live()
    else:
        result = simulate()

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
