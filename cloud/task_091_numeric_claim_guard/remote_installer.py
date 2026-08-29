#!/usr/bin/env python3
"""Fail-closed installer for CRM-NUMERIC-SINGLE-CLAIM-091."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
import traceback
from typing import Any


CONTRACT_ID = "CRM-NUMERIC-SINGLE-CLAIM-091-V1.0"
ROOT = Path(os.environ.get("UA_ART_ROOT", "/home/Carix")).resolve()
REMOTE = ROOT / "autopilot_inbox/cloud/task_091_numeric_claim_guard"
BACKUPS = ROOT / "backups/task_091_numeric_claim_guard"
LOCK = ROOT / ".ua_art_production_writer.lock"
LAST_SUCCESS = REMOTE / "last_successful_install.json"
AI_FILTER = ROOT / "ai_filter.py"
LOCAL_OCR = ROOT / "local_ocr.py"
GUARD = ROOT / "field_claim_guard.py"
DATABASE = ROOT / "crm.db"
INBOX_GUARD = REMOTE / "field_claim_guard.py"
INBOX_PATCHER = REMOTE / "patcher.py"
TARGET_AUTO_NUMBER = "UA-0015"
TARGET_VIN = "KMHE341DBJA475862"
EXPECTED_AI_FILTER_SHA256 = "7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6"
WAIT_SECONDS = 180.0
MAX_FILE = 4 * 1024 * 1024
RECEIPTS = {
    "preflight": REMOTE / "preflight_receipt.json",
    "install": REMOTE / "install_receipt.json",
    "postcheck": REMOTE / "postcheck_receipt.json",
    "rollback": REMOTE / "rollback_receipt.json",
}


class InstallError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def sha(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_FILE:
        raise InstallError("FILE_TOO_LARGE:" + path.name)
    return data


def regular(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise InstallError("UNSAFE_TARGET:" + path.name)


def atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".task091-", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    atomic(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        0o600,
    )


@contextlib.contextmanager
def exclusive_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK, "a+", encoding="utf-8")
    deadline = time.monotonic() + WAIT_SECONDS
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise InstallError("PRODUCTION_LOCK_TIMEOUT")
                time.sleep(0.25)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def load_module(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise InstallError("MODULE_SPEC_INVALID:" + path.name)
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def load_inputs() -> tuple[bytes, bytes, bytes]:
    for path in (AI_FILTER, LOCAL_OCR, INBOX_GUARD, INBOX_PATCHER, DATABASE):
        regular(path)
    ai_bytes, ocr_bytes, guard_bytes = read(AI_FILTER), read(LOCAL_OCR), read(INBOX_GUARD)
    if ROOT == Path("/home/Carix") and EXPECTED_AI_FILTER_SHA256 not in (
        sha(ai_bytes),
    ) and CONTRACT_ID.encode() not in ai_bytes:
        raise InstallError("AI_FILTER_PREIMAGE_DRIFT:" + sha(ai_bytes))
    compile(ai_bytes.decode("utf-8"), str(AI_FILTER), "exec")
    compile(ocr_bytes.decode("utf-8"), str(LOCAL_OCR), "exec")
    compile(guard_bytes.decode("utf-8"), str(INBOX_GUARD), "exec")
    return ai_bytes, ocr_bytes, guard_bytes


def build_candidates(ai_bytes: bytes, ocr_bytes: bytes, guard_bytes: bytes):
    patcher = load_module(INBOX_PATCHER, "task091_patcher")
    if getattr(patcher, "CONTRACT_ID", None) != CONTRACT_ID:
        raise InstallError("PATCHER_CONTRACT_MISMATCH")
    ai_candidate = patcher.patch_ai_filter(ai_bytes.decode("utf-8"))
    ocr_candidate = patcher.patch_local_ocr(ocr_bytes.decode("utf-8"))
    checks = patcher.validate_candidates(ai_candidate, ocr_candidate)
    guard_module = load_module(INBOX_GUARD, "task091_guard_candidate")
    if getattr(guard_module, "CONTRACT_ID", None) != CONTRACT_ID:
        raise InstallError("GUARD_CONTRACT_MISMATCH")
    source = "LPG\n1,999cc\n395,459km\n" + TARGET_VIN
    regression = guard_module.enforce(
        {
            "year": 1999,
            "engine_cc": 1999,
            "mileage_km": 395459,
            "fuel": "LPG",
            "vin": TARGET_VIN,
        },
        source,
    )
    expected = {
        "engine_cc": 1999,
        "mileage_km": 395459,
        "fuel": "LPG",
        "vin": TARGET_VIN,
    }
    if regression != expected:
        raise InstallError("REGRESSION_CASE_FAIL:" + repr(regression))
    independently_repeated = guard_module.enforce(
        {"year": 1999, "engine_cc": 1999},
        "Год: 1999\nОбъём: 1999cc",
    )
    if independently_repeated != {"year": 1999, "engine_cc": 1999}:
        raise InstallError("DISTINCT_OCCURRENCES_FAIL")
    return {
        "ai_filter.py": ai_candidate.encode(),
        "local_ocr.py": ocr_candidate.encode(),
        "field_claim_guard.py": guard_bytes,
    }, {"patch_checks": checks, "reported_regression": regression}


def database_snapshot() -> dict[str, Any]:
    connection = sqlite3.connect("file:%s?mode=ro" % DATABASE, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        rows = [
            dict(row) for row in connection.execute(
                "SELECT * FROM cars ORDER BY id"
            ).fetchall()
        ]
    finally:
        connection.close()
    target = [
        row for row in rows
        if str(row.get("auto_number") or "").upper() == TARGET_AUTO_NUMBER
        and str(row.get("vin") or "").upper() == TARGET_VIN
    ]
    if quick != "ok":
        raise InstallError("CRM_QUICK_CHECK:" + quick)
    if len(target) != 1:
        raise InstallError("UA0015_EXACT_ROW_COUNT:%d" % len(target))
    return {
        "quick_check": quick,
        "cars_count": len(rows),
        "rows": rows,
        "rows_sha256": sha(json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)),
        "target": target[0],
    }


def sqlite_backup(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(DATABASE, timeout=30)
    target = sqlite3.connect(destination, timeout=30)
    try:
        source.execute("PRAGMA busy_timeout=30000")
        source.backup(target)
        target.commit()
        if str(target.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise InstallError("BACKUP_QUICK_CHECK_FAIL")
    finally:
        target.close()
        source.close()


def create_backup(ai: bytes, ocr: bytes) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = BACKUPS / stamp
    root.mkdir(parents=True, exist_ok=False)
    atomic(root / "ai_filter.py", ai, 0o600)
    atomic(root / "local_ocr.py", ocr, 0o600)
    if GUARD.exists():
        regular(GUARD)
        atomic(root / "field_claim_guard.py", read(GUARD), 0o600)
    else:
        atomic(root / "field_claim_guard.absent", b"absent\n", 0o600)
    sqlite_backup(root / "crm.db")
    atomic_json(root / "manifest.json", {
        "contract_id": CONTRACT_ID,
        "created_at_utc": utc_now(),
        "ai_filter_sha256": sha(ai),
        "local_ocr_sha256": sha(ocr),
        "database_backup": "crm.db",
    })
    return root


def migrate_ua0015() -> dict[str, Any]:
    connection = sqlite3.connect(DATABASE, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id,auto_number,vin,year,engine_cc,mileage_km,fuel,published "
            "FROM cars WHERE upper(auto_number)=? AND upper(vin)=?",
            (TARGET_AUTO_NUMBER, TARGET_VIN),
        ).fetchone()
        if row is None:
            raise InstallError("UA0015_ROW_MISSING")
        before = dict(row)
        if int(before.get("engine_cc") or 0) != 1999:
            raise InstallError("UA0015_ENGINE_PREIMAGE:" + str(before.get("engine_cc")))
        if int(before.get("published") or 0) != 0:
            raise InstallError("UA0015_NOT_DRAFT")
        old_year = str(before.get("year") or "").strip()
        changed = False
        if old_year == "1999":
            now = utc_now()
            connection.execute(
                "UPDATE cars SET year='', updated_at=? WHERE id=? AND year='1999'",
                (now, int(before["id"])),
            )
            if connection.total_changes != 1:
                raise InstallError("UA0015_YEAR_CAS_FAIL")
            tables = {
                str(item[0]) for item in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "audit" in tables:
                connection.execute(
                    "INSERT INTO audit(actor_id,action,entity_type,entity_id,field,"
                    "old_value,new_value,created_at) VALUES(NULL,?,?,?,?,?,?,?)",
                    (
                        "task091_numeric_single_claim",
                        "cars",
                        int(before["id"]),
                        "year",
                        "1999",
                        "",
                        now,
                    ),
                )
            changed = True
        elif old_year:
            raise InstallError("UA0015_YEAR_PREIMAGE:" + old_year)
        after = dict(connection.execute(
            "SELECT id,auto_number,vin,year,engine_cc,mileage_km,fuel,published "
            "FROM cars WHERE id=?", (int(before["id"]),)
        ).fetchone())
        if str(after.get("year") or "").strip():
            raise InstallError("UA0015_YEAR_READBACK")
        if int(after.get("engine_cc") or 0) != 1999:
            raise InstallError("UA0015_ENGINE_CHANGED")
        if str(connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise InstallError("CRM_QUICK_CHECK_AFTER_MIGRATION")
        connection.execute("COMMIT")
        return {"changed": changed, "before": before, "after": after}
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()


def restore_database(backup: Path) -> None:
    source = sqlite3.connect(backup, timeout=30)
    destination = sqlite3.connect(DATABASE, timeout=30)
    try:
        destination.execute("PRAGMA busy_timeout=30000")
        source.backup(destination)
        destination.commit()
        if str(destination.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise InstallError("RESTORED_DB_QUICK_CHECK_FAIL")
    finally:
        destination.close()
        source.close()


def restore_backup(root: Path) -> dict[str, Any]:
    if not str(root.resolve()).startswith(str(BACKUPS.resolve()) + os.sep):
        raise InstallError("ROLLBACK_SCOPE")
    for name, target in (("ai_filter.py", AI_FILTER), ("local_ocr.py", LOCAL_OCR)):
        source = root / name
        regular(source)
        mode = target.stat().st_mode & 0o777
        atomic(target, read(source), mode)
        py_compile.compile(str(target), doraise=True)
    saved_guard = root / "field_claim_guard.py"
    if saved_guard.exists():
        atomic(GUARD, read(saved_guard), 0o644)
        py_compile.compile(str(GUARD), doraise=True)
    else:
        if not (root / "field_claim_guard.absent").is_file():
            raise InstallError("GUARD_BACKUP_STATE_MISSING")
        if GUARD.exists():
            regular(GUARD)
            GUARD.unlink()
    restore_database(root / "crm.db")
    return {"backup_root": str(root), "restored": True}


def compare_allowed_change(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before["cars_count"] != after["cars_count"]:
        raise InstallError("CARS_COUNT_CHANGED")
    before_rows = {int(row["id"]): dict(row) for row in before["rows"]}
    after_rows = {int(row["id"]): dict(row) for row in after["rows"]}
    if before_rows.keys() != after_rows.keys():
        raise InstallError("CAR_IDS_CHANGED")
    target_id = int(before["target"]["id"])
    for identifier in before_rows:
        left, right = before_rows[identifier], after_rows[identifier]
        if identifier == target_id:
            left["year"] = ""
            right["year"] = str(right.get("year") or "")
            left["updated_at"] = right.get("updated_at")
        if left != right:
            raise InstallError("UNEXPECTED_CAR_CHANGE:%d" % identifier)


def preflight() -> dict[str, Any]:
    result = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "mode": "READ_ONLY_PREFLIGHT",
        "production_write": False,
        "crm_write": False,
        "errors": [],
    }
    try:
        ai, ocr, guard = load_inputs()
        candidates, checks = build_candidates(ai, ocr, guard)
        database = database_snapshot()
        target = database["target"]
        if int(target.get("engine_cc") or 0) != 1999:
            raise InstallError("UA0015_ENGINE_PREFLIGHT")
        if str(target.get("year") or "").strip() not in ("", "1999"):
            raise InstallError("UA0015_YEAR_PREFLIGHT")
        result.update({
            "status": "PASS",
            "checks": checks,
            "candidate_sha256": {name: sha(value) for name, value in candidates.items()},
            "database": {key: value for key, value in database.items() if key != "rows"},
        })
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    return result


def install() -> dict[str, Any]:
    result = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "mode": "ATOMIC_INSTALL",
        "production_write": False,
        "crm_write": False,
        "errors": [],
        "rollback": None,
    }
    backup: Path | None = None
    try:
        ai, ocr, guard = load_inputs()
        candidates, checks = build_candidates(ai, ocr, guard)
        before = database_snapshot()
        backup = create_backup(ai, ocr)
        result["backup_root"] = str(backup)
        preimages = {AI_FILTER: ai, LOCAL_OCR: ocr}
        for path, expected in preimages.items():
            if read(path) != expected:
                raise InstallError("PREIMAGE_CHANGED_UNDER_LOCK:" + path.name)
        atomic(GUARD, candidates["field_claim_guard.py"], 0o644)
        atomic(AI_FILTER, candidates["ai_filter.py"], AI_FILTER.stat().st_mode & 0o777)
        atomic(LOCAL_OCR, candidates["local_ocr.py"], LOCAL_OCR.stat().st_mode & 0o777)
        for path in (GUARD, AI_FILTER, LOCAL_OCR):
            py_compile.compile(str(path), doraise=True)
        migration = migrate_ua0015()
        after = database_snapshot()
        compare_allowed_change(before, after)
        if read(AI_FILTER) != candidates["ai_filter.py"]:
            raise InstallError("AI_FILTER_READBACK")
        if read(LOCAL_OCR) != candidates["local_ocr.py"]:
            raise InstallError("LOCAL_OCR_READBACK")
        if read(GUARD) != candidates["field_claim_guard.py"]:
            raise InstallError("GUARD_READBACK")
        result.update({
            "status": "PASS",
            "production_write": True,
            "crm_write": bool(migration["changed"]),
            "checks": checks,
            "migration": migration,
            "before_sha256": {"ai_filter.py": sha(ai), "local_ocr.py": sha(ocr)},
            "after_sha256": {
                "ai_filter.py": sha(candidates["ai_filter.py"]),
                "local_ocr.py": sha(candidates["local_ocr.py"]),
                "field_claim_guard.py": sha(candidates["field_claim_guard.py"]),
            },
            "database_after": {key: value for key, value in after.items() if key != "rows"},
        })
        atomic_json(LAST_SUCCESS, {
            "contract_id": CONTRACT_ID,
            "backup_root": str(backup),
            "installed_at_utc": utc_now(),
        })
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
        result["traceback"] = traceback.format_exc(limit=8)
        if backup is not None:
            try:
                result["rollback"] = restore_backup(backup)
            except Exception as rollback_exc:
                result["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
    return result


def postcheck() -> dict[str, Any]:
    result = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "mode": "READ_ONLY_POSTCHECK",
        "production_write": False,
        "crm_write": False,
        "errors": [],
    }
    try:
        for path in (GUARD, AI_FILTER, LOCAL_OCR):
            regular(path)
            py_compile.compile(str(path), doraise=True)
        ai_text = AI_FILTER.read_text(encoding="utf-8")
        ocr_text = LOCAL_OCR.read_text(encoding="utf-8")
        if ai_text.count(CONTRACT_ID) != 1 or ocr_text.count(CONTRACT_ID) != 1:
            raise InstallError("PATCH_MARKER_INVALID")
        guard = load_module(GUARD, "task091_guard_postcheck")
        regression = guard.enforce(
            {"year": 1999, "engine_cc": 1999, "mileage_km": 395459},
            "1,999cc\n395,459km",
        )
        if regression != {"engine_cc": 1999, "mileage_km": 395459}:
            raise InstallError("POSTCHECK_REGRESSION_FAIL")
        database = database_snapshot()
        target = database["target"]
        if str(target.get("year") or "").strip():
            raise InstallError("UA0015_YEAR_NOT_EMPTY")
        if int(target.get("engine_cc") or 0) != 1999:
            raise InstallError("UA0015_ENGINE_NOT_1999")
        result.update({
            "status": "PASS",
            "regression": regression,
            "database": {key: value for key, value in database.items() if key != "rows"},
            "markers": {"ai_filter": 1, "local_ocr": 1, "guard": 1},
        })
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    return result


def rollback() -> dict[str, Any]:
    result = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_write": True,
        "errors": [],
    }
    try:
        pointer = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        restored = restore_backup(Path(pointer["backup_root"]))
        result.update({"status": "PASS", "restored": restored})
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=tuple(RECEIPTS))
    arguments = parser.parse_args(argv)
    REMOTE.mkdir(parents=True, exist_ok=True)
    if arguments.mode in ("install", "rollback"):
        with exclusive_lock():
            value = {"install": install, "rollback": rollback}[arguments.mode]()
    else:
        value = {"preflight": preflight, "postcheck": postcheck}[arguments.mode]()
    value["completed_at_utc"] = utc_now()
    atomic_json(RECEIPTS[arguments.mode], value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
