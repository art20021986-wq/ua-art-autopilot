#!/usr/bin/env python3
"""Atomic PythonAnywhere installer for TASK 082."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import fcntl
import hashlib
import importlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from typing import Any


CONTRACT_ID = "UA-0011-CATALOG-FERRY-REPAIR-001-V1.0"
ROOT = pathlib.Path("/home/Carix")
REMOTE = ROOT / "autopilot_inbox/cloud/task_082_catalog_stage_repair"
BACKUPS = REMOTE / "backups"
RECEIPTS = {
    "install": REMOTE / "install_receipt.json",
    "rollback": REMOTE / "rollback_receipt.json",
    "postcheck": REMOTE / "postcheck_receipt.json",
}
LOCK = ROOT / ".task082_catalog_stage_repair.lock"
SOURCE_INBOX = {
    ROOT / "catalog_stage_guard_core.py": REMOTE / "catalog_stage_guard_core.py",
    ROOT / "catalog_stage_guard_runtime.py": REMOTE / "catalog_stage_guard_runtime.py",
}
PUBLISHER = ROOT / "publikaciya.py"
DB_MODULE = ROOT / "db.py"
DB_PATH = ROOT / "crm.db"
CATALOGS = (ROOT / "video/katalog.html", ROOT / "site/katalog.html")
MANAGED = (DB_MODULE, PUBLISHER, *SOURCE_INBOX.keys(), *CATALOGS)
START_MARKER = "# UA-0011-CATALOG-FERRY-REPAIR-001-V1.0:START"
END_MARKER = "# UA-0011-CATALOG-FERRY-REPAIR-001-V1.0:END"
DB_START_MARKER = "# UA-0011-STAGE-REGRESSION-GUARD-001-V1.0:START"
DB_END_MARKER = "# UA-0011-STAGE-REGRESSION-GUARD-001-V1.0:END"
TARGET = "UA-0011"
TARGET_VIN = "KMHE341DBKA544289"
TARGET_STATUS = "sea_loaded"
MAX_BYTES = 24 * 1024 * 1024


class InstallError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise InstallError("FILE_TOO_LARGE:" + str(path))
    return data


def atomic(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False)
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def published_rows() -> list[dict[str, Any]]:
    con = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        rows = [dict(row) for row in con.execute(
            "SELECT * FROM cars WHERE published=1 ORDER BY auto_number, id"
        ).fetchall()]
    finally:
        con.close()
    if quick != "ok":
        raise InstallError("CRM_QUICK_CHECK:" + str(quick))
    return rows


def rows_hash(rows: list[dict[str, Any]]) -> str:
    data = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    return sha(data)


def published_rows_hash() -> tuple[str, int]:
    rows = published_rows()
    return rows_hash(rows), len(rows)


def protected_pages() -> dict[str, str]:
    result = {}
    for parent in (ROOT / "video", ROOT / "site"):
        for path in sorted(parent.glob("UA-*.html")):
            result[str(path)] = sha(read(path))
    return result


def ua0011_media() -> dict[str, str]:
    result = {}
    candidates = []
    for parent in (ROOT / "video", ROOT / "site"):
        candidates.extend(parent.glob("UA-0011.*"))
        candidates.extend((parent / "foto/UA-0011").rglob("*") if (parent / "foto/UA-0011").exists() else [])
    for path in sorted(set(candidates)):
        if path.is_file() and not path.name.endswith(".html"):
            result[str(path)] = sha(path.read_bytes())
    return result


def strip_wrapper(source: str) -> str:
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER) + r"\s*",
        re.S,
    )
    return pattern.sub("", source)


def publisher_wrapper() -> str:
    return r'''
# UA-0011-CATALOG-FERRY-REPAIR-001-V1.0:START
_ua082_opublikovat_original = opublikovat

def opublikovat(kod, proba=False):
    result = _ua082_opublikovat_original(kod, proba)
    try:
        ok = bool(result[0]) if isinstance(result, (tuple, list)) and result else bool(result)
    except Exception:
        ok = False
    if proba or not ok:
        return result
    try:
        from catalog_stage_guard_runtime import enforce_live_catalog as _ua082_enforce
        _ua082_enforce(kod)
    except Exception as exc:
        return False, ("Публикация отменена: каталог не прошёл проверку этапа/фото (%s). "
                       "Старая версия каталога сохранена." % exc)
    return result
# UA-0011-CATALOG-FERRY-REPAIR-001-V1.0:END
'''


def patch_publisher(source: str) -> str:
    base = strip_wrapper(source).rstrip() + "\n"
    tree = ast.parse(base)
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "opublikovat"
    ]
    if len(definitions) != 1:
        raise InstallError("PUBLISHER_DEFINITION_COUNT:%d" % len(definitions))
    candidate = base + publisher_wrapper().lstrip()
    compile(candidate, "publikaciya.py", "exec")
    if candidate.count(START_MARKER) != 1 or candidate.count(END_MARKER) != 1:
        raise InstallError("PUBLISHER_MARKER_COUNT")
    return candidate


def db_guard_wrapper() -> str:
    return r'''
# UA-0011-STAGE-REGRESSION-GUARD-001-V1.0:START
_ua082_update_card_field_original = update_card_field

def _ua082_stage_number(value):
    text = str(value or "").strip().lower()
    if text.startswith("kr_") or text in ("kr", "korea"):
        return 1
    if text.startswith("sea_") or text.startswith("sold_transit") or text in ("sea", "ferry", "more"):
        return 2
    if text.startswith("ge_") or text in ("ge", "georgia", "gruzia"):
        return 3
    if text.startswith("ua_") or text in ("ua", "kyiv", "kiev"):
        return 4
    return None

def _ua082_stage_floor(card):
    floor = 1
    if card.get("sea_container") or card.get("sea_date_out"):
        floor = 2
    if any(card.get(name) for name in ("ge_port", "ge_arrived", "ge_released", "ge_to_kyiv_at")):
        floor = 3
    if any(card.get(name) for name in ("ua_delivered", "ua_handed")):
        floor = 4
    return floor

def update_card_field(table: str, card_id: int, field: str, value, actor_id: int):
    if table == "cars" and field == "status":
        card = get_card(table, card_id) or {}
        proposed = _ua082_stage_number(value)
        floor = _ua082_stage_floor(card)
        if proposed is not None and proposed < floor:
            log_action(actor_id, "stage_regression_blocked", table, card_id, field,
                       card.get("status"), value)
            logging.warning(
                "blocked stage regression card=%s from=%s to=%s evidence_floor=%s",
                card_id, card.get("status"), value, floor,
            )
            return False
    return _ua082_update_card_field_original(table, card_id, field, value, actor_id)
# UA-0011-STAGE-REGRESSION-GUARD-001-V1.0:END
'''


def patch_db(source: str) -> str:
    pattern = re.compile(
        re.escape(DB_START_MARKER) + r".*?" + re.escape(DB_END_MARKER) + r"\s*",
        re.S,
    )
    base = pattern.sub("", source).rstrip() + "\n"
    tree = ast.parse(base)
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "update_card_field"
    ]
    if len(definitions) != 1:
        raise InstallError("DB_UPDATE_DEFINITION_COUNT:%d" % len(definitions))
    candidate = base + db_guard_wrapper().lstrip()
    compile(candidate, "db.py", "exec")
    if candidate.count(DB_START_MARKER) != 1 or candidate.count(DB_END_MARKER) != 1:
        raise InstallError("DB_GUARD_MARKER_COUNT")
    return candidate


def target_row(con: sqlite3.Connection) -> dict[str, Any]:
    row = con.execute("SELECT * FROM cars WHERE auto_number=?", (TARGET,)).fetchone()
    if row is None:
        raise InstallError("UA0011_ROW_MISSING")
    return dict(row)


def validate_target(row: dict[str, Any]) -> None:
    if str(row.get("vin") or "").upper() != TARGET_VIN:
        raise InstallError("UA0011_VIN_MISMATCH")
    if int(row.get("published") or 0) != 1:
        raise InstallError("UA0011_NOT_PUBLISHED")
    if not str(row.get("sea_container") or "").strip():
        raise InstallError("UA0011_CONTAINER_MISSING")


def repair_target_stage() -> dict[str, Any]:
    con = sqlite3.connect(str(DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("BEGIN IMMEDIATE")
        before = target_row(con)
        validate_target(before)
        current = str(before.get("status") or "")
        if current not in ("kr_bought", TARGET_STATUS):
            raise InstallError("UA0011_UNEXPECTED_STATUS:" + current)
        changed = current != TARGET_STATUS
        audit_id = None
        repaired_at = before.get("updated_at")
        if changed:
            repaired_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            con.execute(
                "UPDATE cars SET status=?, updated_at=? WHERE id=? AND status=?",
                (TARGET_STATUS, repaired_at, before["id"], current),
            )
            if con.total_changes != 1:
                raise InstallError("UA0011_STAGE_UPDATE_RACE")
            cursor = con.execute(
                "INSERT INTO audit(actor_id,action,entity_type,entity_id,field,old_value,new_value,created_at) "
                "VALUES(NULL,?,?,?,?,?,?,?)",
                ("task082_stage_repair", "cars", before["id"], "status",
                 current, TARGET_STATUS, repaired_at),
            )
            audit_id = cursor.lastrowid
        after = target_row(con)
        validate_target(after)
        if after.get("status") != TARGET_STATUS:
            raise InstallError("UA0011_STAGE_REPAIR_READBACK")
        con.commit()
        return {
            "changed": changed,
            "auto_number": TARGET,
            "field": "status",
            "before_status": current,
            "after_status": TARGET_STATUS,
            "before_updated_at": before.get("updated_at"),
            "after_updated_at": after.get("updated_at"),
            "sea_container": after.get("sea_container"),
            "audit_id": audit_id,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def rollback_target_stage(change: dict[str, Any] | None) -> dict[str, Any]:
    if not change or not change.get("changed"):
        return {"changed": False, "reason": "stage_was_already_correct"}
    con = sqlite3.connect(str(DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("BEGIN IMMEDIATE")
        current = target_row(con)
        expected = change.get("after_status")
        expected_at = change.get("after_updated_at")
        if current.get("status") != expected or current.get("updated_at") != expected_at:
            raise InstallError("UA0011_ROLLBACK_DRIFT")
        rolled_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        con.execute(
            "UPDATE cars SET status=?, updated_at=? WHERE id=?",
            (change.get("before_status"), change.get("before_updated_at"), current["id"]),
        )
        con.execute(
            "INSERT INTO audit(actor_id,action,entity_type,entity_id,field,old_value,new_value,created_at) "
            "VALUES(NULL,?,?,?,?,?,?,?)",
            ("task082_stage_rollback", "cars", current["id"], "status",
             expected, change.get("before_status"), rolled_at),
        )
        con.commit()
        return {"changed": True, "status": change.get("before_status")}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def verify_rows_change(before: list[dict[str, Any]], after: list[dict[str, Any]],
                       repair: dict[str, Any]) -> None:
    old = {str(row.get("auto_number") or ""): row for row in before}
    new = {str(row.get("auto_number") or ""): row for row in after}
    if set(old) != set(new):
        raise InstallError("CRM_ROW_SET_CHANGED")
    for identifier in old:
        if identifier != TARGET and old[identifier] != new[identifier]:
            raise InstallError("UNRELATED_CRM_ROW_CHANGED:" + identifier)
    before_target = dict(old[TARGET])
    after_target = dict(new[TARGET])
    if repair.get("changed"):
        for field in ("status", "updated_at"):
            before_target.pop(field, None)
            after_target.pop(field, None)
        if before_target != after_target:
            raise InstallError("UA0011_UNEXPECTED_FIELD_CHANGED")
    elif before_target != after_target:
        raise InstallError("UA0011_CHANGED_WHEN_ALREADY_CORRECT")
    if new[TARGET].get("status") != TARGET_STATUS:
        raise InstallError("UA0011_NOT_FERRY_AFTER_REPAIR")


def create_backup() -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = BACKUPS / (stamp + "-" + uuid.uuid4().hex[:12])
    manifest = {}
    for path in MANAGED:
        exists = path.is_file()
        item = {"path": str(path), "exists": exists}
        if exists:
            data = read(path)
            target = root / path.relative_to(ROOT)
            atomic(target, data, path.stat().st_mode & 0o777)
            item.update({"sha256": sha(data), "mode": path.stat().st_mode & 0o777})
        manifest[str(path)] = item
    atomic_json(root / "manifest.json", manifest)
    return root


def restore(backup_root: pathlib.Path) -> list[str]:
    manifest_path = backup_root / "manifest.json"
    if not manifest_path.is_file() or BACKUPS not in backup_root.parents:
        raise InstallError("BACKUP_MANIFEST_INVALID")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = []
    for path in MANAGED:
        item = manifest.get(str(path))
        if not item:
            raise InstallError("BACKUP_ENTRY_MISSING:" + str(path))
        if item["exists"]:
            data = read(backup_root / path.relative_to(ROOT))
            if not path.is_file() or read(path) != data:
                atomic(path, data, int(item.get("mode") or 0o644))
                changed.append(str(path))
        elif path.exists():
            path.unlink()
            changed.append(str(path))
    return changed


def import_runtime():
    sys.path.insert(0, str(ROOT))
    for name in ("catalog_stage_guard_runtime", "catalog_stage_guard_core"):
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return importlib.import_module("catalog_stage_guard_runtime")


def verify_catalogs(runtime, expected_rows_hash: str) -> dict[str, Any]:
    evidence = runtime.enforce_live_catalog("UA-0011", dry_run=True)
    if evidence.get("status") != "PASS":
        raise InstallError("RUNTIME_DRY_RUN_FAIL")
    if evidence.get("rows_sha256_before") != expected_rows_hash:
        raise InstallError("RUNTIME_DB_HASH_MISMATCH")
    for variant, item in (evidence.get("catalogs") or {}).items():
        if item.get("before_sha256") != item.get("candidate_sha256"):
            raise InstallError("RUNTIME_NOT_IDEMPOTENT:" + variant)
        card = ((item.get("audit") or {}).get("cards") or {}).get("UA-0011") or {}
        if not (card.get("stage") == 2 and card.get("category") == "more"
                and card.get("template") and card.get("absolute_photo")):
            raise InstallError("UA0011_POSTCHECK:" + variant)
    return evidence


def run_install() -> dict[str, Any]:
    before_rows_value = published_rows()
    before_rows = rows_hash(before_rows_value)
    row_count = len(before_rows_value)
    before_pages = protected_pages()
    before_media = ua0011_media()
    source = PUBLISHER.read_text(encoding="utf-8")
    publisher_candidate = patch_publisher(source)
    db_candidate = patch_db(DB_MODULE.read_text(encoding="utf-8"))
    for destination, source_path in SOURCE_INBOX.items():
        payload = read(source_path)
        compile(payload.decode("utf-8"), destination.name, "exec")

    backup_root = create_backup()
    changed = []
    stage_repair = None
    try:
        for destination, source_path in SOURCE_INBOX.items():
            payload = read(source_path)
            if not destination.is_file() or read(destination) != payload:
                atomic(destination, payload, destination.stat().st_mode & 0o777 if destination.exists() else 0o644)
                changed.append(str(destination))
        if publisher_candidate.encode() != read(PUBLISHER):
            atomic(PUBLISHER, publisher_candidate.encode(), PUBLISHER.stat().st_mode & 0o777)
            changed.append(str(PUBLISHER))
        if db_candidate.encode() != read(DB_MODULE):
            atomic(DB_MODULE, db_candidate.encode(), DB_MODULE.stat().st_mode & 0o777)
            changed.append(str(DB_MODULE))

        stage_repair = repair_target_stage()

        runtime = import_runtime()
        repair = runtime.enforce_live_catalog("UA-0011")
        changed.extend(repair.get("changed_paths") or [])
        after_rows_value = published_rows()
        after_rows = rows_hash(after_rows_value)
        after_count = len(after_rows_value)
        if after_count != row_count:
            raise InstallError("CRM_ROW_COUNT_CHANGED")
        verify_rows_change(before_rows_value, after_rows_value, stage_repair)
        if protected_pages() != before_pages:
            raise InstallError("INDIVIDUAL_PAGES_CHANGED")
        if ua0011_media() != before_media:
            raise InstallError("UA0011_MEDIA_CHANGED")
        postcheck = verify_catalogs(runtime, before_rows)
        return {
            "contract_id": CONTRACT_ID,
            "status": "PASS",
            "mode": "INSTALL",
            "production_write": True,
            "crm_write": bool(stage_repair.get("changed")),
            "crm_scope": ["cars.UA-0011.status", "cars.UA-0011.updated_at", "audit.task082_stage_repair"]
            if stage_repair.get("changed") else [],
            "media_write": False,
            "llm_tokens": 0,
            "backup_root": str(backup_root),
            "changed_paths": sorted(set(changed)),
            "published_rows": row_count,
            "rows_sha256_before": before_rows,
            "rows_sha256_after": after_rows,
            "stage_repair": stage_repair,
            "db_stage_guard_installed": DB_START_MARKER in DB_MODULE.read_text(encoding="utf-8"),
            "protected_pages": len(before_pages),
            "ua0011_media_files": len(before_media),
            "repair": repair,
            "postcheck": postcheck,
        }
    except Exception:
        restore(backup_root)
        rollback_target_stage(stage_repair)
        raise


def run_postcheck() -> dict[str, Any]:
    rows_hash, row_count = published_rows_hash()
    db_source = DB_MODULE.read_text(encoding="utf-8")
    if db_source.count(DB_START_MARKER) != 1 or db_source.count(DB_END_MARKER) != 1:
        raise InstallError("DB_STAGE_GUARD_NOT_INSTALLED")
    con = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        row = target_row(con)
    finally:
        con.close()
    validate_target(row)
    if row.get("status") != TARGET_STATUS:
        raise InstallError("UA0011_POSTRESTART_STATUS:" + str(row.get("status")))
    runtime = import_runtime()
    value = verify_catalogs(runtime, rows_hash)
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "POSTCHECK",
        "read_only": True,
        "production_write": False,
        "crm_write": False,
        "media_write": False,
        "llm_tokens": 0,
        "published_rows": row_count,
        "rows_sha256": rows_hash,
        "ua0011": {
            "status": row.get("status"), "stage": 2,
            "sea_container": row.get("sea_container"),
        },
        "db_stage_guard_installed": True,
        "runtime": value,
    }


def run_rollback() -> dict[str, Any]:
    receipt = json.loads(RECEIPTS["install"].read_text(encoding="utf-8"))
    backup_root = pathlib.Path(str(receipt.get("backup_root") or ""))
    restored = restore(backup_root)
    stage = rollback_target_stage(receipt.get("stage_repair"))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_write": bool(stage.get("changed")),
        "media_write": False,
        "backup_root": str(backup_root),
        "restored": restored,
        "stage_rollback": stage,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install", "postcheck", "rollback"))
    args = parser.parse_args()
    REMOTE.mkdir(parents=True, exist_ok=True)
    LOCK.touch(exist_ok=True)
    with LOCK.open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            value = {"install": run_install, "postcheck": run_postcheck, "rollback": run_rollback}[args.mode]()
        except Exception as exc:
            value = {
                "contract_id": CONTRACT_ID,
                "status": "FAIL",
                "mode": args.mode.upper(),
                "production_write": args.mode != "postcheck",
                "crm_write": False,
                "media_write": False,
                "llm_tokens": 0,
                "errors": [type(exc).__name__ + ":" + str(exc)],
            }
        atomic_json(RECEIPTS[args.mode], value)
    print(json.dumps({"status": value["status"], "mode": value["mode"],
                      "errors": value.get("errors", [])}, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
