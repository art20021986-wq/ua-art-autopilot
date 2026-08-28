#!/usr/bin/env python3
"""Apply the owner's three explicit UA-0011 values atomically."""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile


BASE = pathlib.Path("/home/Carix")
DB_PATH = BASE / "crm.db"
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_065"
RECEIPT = SAFE / "voice_fields_repair_receipt.json"
ROLLBACK_RECEIPT = SAFE / "voice_fields_repair_rollback_receipt.json"
CONTRACT = "CRM-VOICE-FIELDS-003"
DESIRED = {"fuel": "LPI", "engine_cc": 2000, "color": "белый"}
DEPLOY_LOCK = BASE / ".task066_stage_anchor.lock"


class RepairError(RuntimeError):
    pass


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def row_state(con):
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM cars WHERE auto_number=? ORDER BY id", ("UA-0011",)).fetchall()
    if len(rows) != 1 or rows[0]["id"] != 18:
        raise RepairError("UA0011_IDENTITY_MISMATCH")
    row = dict(rows[0])
    protected = {key: value for key, value in row.items()
                 if key not in {"fuel", "engine_cc", "color", "updated_at"}}
    protected_hash = hashlib.sha256(json.dumps(
        protected, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return {"id": row["id"], "auto_number": row["auto_number"],
            "fuel": row.get("fuel"), "engine_cc": row.get("engine_cc"),
            "color": row.get("color"), "updated_at": row.get("updated_at"),
            "protected_sha256": protected_hash}


def connect_module():
    if str(BASE) not in sys.path:
        sys.path.insert(0, str(BASE))
    import db
    return db


def restore(previous, receipt_path):
    db = connect_module()
    with db.connect() as con:
        current = row_state(con)
        current_values = {key: current[key] for key in DESIRED}
        if current_values != DESIRED:
            raise RepairError("ROLLBACK_TARGET_CHANGED")
        con.execute(
            "UPDATE cars SET fuel=?,engine_cc=?,color=?,updated_at=? "
            "WHERE id=? AND auto_number=?",
            (previous.get("fuel"), previous.get("engine_cc"), previous.get("color"),
             previous.get("updated_at"), 18, "UA-0011"),
        )
    with db.connect() as con:
        after = row_state(con)
    result = {"task_id": "task_065", "contract_id": CONTRACT,
              "status": "PASS", "mode": "ROLLBACK", "after": after,
              "finished_at_utc": now()}
    atomic_json(receipt_path, result)
    return result


def main():
    if "--rollback" in sys.argv:
        if not RECEIPT.exists():
            raise RepairError("REPAIR_RECEIPT_MISSING")
        previous = json.loads(RECEIPT.read_text(encoding="utf-8")).get("before")
        if not previous:
            raise RepairError("REPAIR_BEFORE_MISSING")
        restore(previous, ROLLBACK_RECEIPT)
        return 0

    result = {"task_id": "task_065", "contract_id": CONTRACT,
              "status": "FAIL", "mode": "UA0011_EXPLICIT_OWNER_VALUES",
              "columns_changed": sorted(DESIRED), "desired": DESIRED,
              "errors": [], "started_at_utc": now(), "llm_tokens": 0,
              "site_write": False}
    before = None
    changed = False
    deploy_guard = None
    try:
        deploy_guard = open(DEPLOY_LOCK, "a+", encoding="utf-8")
        fcntl.flock(deploy_guard.fileno(), fcntl.LOCK_EX)
        db = connect_module()
        with db.connect() as con:
            before = row_state(con)
            result["before"] = before
            before_values = {key: before[key] for key in DESIRED}
            if before_values != DESIRED:
                timestamp = now().replace("Z", "")
                cursor = con.execute(
                    "UPDATE cars SET fuel=?,engine_cc=?,color=?,updated_at=? "
                    "WHERE id=? AND auto_number=?",
                    (DESIRED["fuel"], DESIRED["engine_cc"], DESIRED["color"],
                     timestamp, 18, "UA-0011"),
                )
                if cursor.rowcount != 1:
                    raise RepairError("UA0011_UPDATE_COUNT_INVALID")
                changed = True
        with db.connect() as con:
            after = row_state(con)
            quick = con.execute("PRAGMA quick_check").fetchone()[0]
        result["after"] = after
        result["quick_check"] = quick
        actual = {key: after[key] for key in DESIRED}
        if actual != DESIRED:
            raise RepairError("UA0011_VALUES_NOT_SAVED")
        if before["protected_sha256"] != after["protected_sha256"]:
            raise RepairError("PROTECTED_FIELDS_CHANGED")
        if quick != "ok":
            raise RepairError("DB_QUICK_CHECK_FAILED")
        result["changed"] = changed
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
        if changed and before:
            try:
                result["rollback"] = restore(before, ROLLBACK_RECEIPT)
            except Exception as rollback_exc:
                result["errors"].append("ROLLBACK_" + type(rollback_exc).__name__
                                        + ":" + str(rollback_exc))
    result["finished_at_utc"] = now()
    if deploy_guard is not None:
        try:
            fcntl.flock(deploy_guard.fileno(), fcntl.LOCK_UN)
            deploy_guard.close()
        except Exception:
            pass
    atomic_json(RECEIPT, result)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
