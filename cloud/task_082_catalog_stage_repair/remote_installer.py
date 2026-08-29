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
CATALOGS = (ROOT / "video/katalog.html", ROOT / "site/katalog.html")
MANAGED = (PUBLISHER, *SOURCE_INBOX.keys(), *CATALOGS)
START_MARKER = "# UA-0011-CATALOG-FERRY-REPAIR-001-V1.0:START"
END_MARKER = "# UA-0011-CATALOG-FERRY-REPAIR-001-V1.0:END"
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


def published_rows_hash() -> tuple[str, int]:
    con = sqlite3.connect("file:%s?mode=ro" % (ROOT / "crm.db"), uri=True, timeout=20)
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
    data = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    return sha(data), len(rows)


def _ua0011_row(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT * FROM cars WHERE auto_number = ? ORDER BY id", ("UA-0011",)
    ).fetchall()
    if len(rows) != 1:
        raise InstallError("UA0011_ROW_COUNT:%d" % len(rows))
    return dict(rows[0])


def _row_hash(row: dict[str, Any]) -> str:
    return sha(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode())


def _validate_ua0011_identity(row: dict[str, Any]) -> int:
    vin = re.sub(r"[^A-Z0-9]", "", str(row.get("vin") or "").upper())
    try:
        photos = json.loads(row.get("photos") or "[]")
    except Exception as exc:
        raise InstallError("UA0011_PHOTOS_INVALID") from exc
    if vin != "KMHE341DBKA544289":
        raise InstallError("UA0011_VIN_MISMATCH")
    if int(row.get("published") or 0) != 1:
        raise InstallError("UA0011_NOT_PUBLISHED")
    if not isinstance(photos, list) or not photos:
        raise InstallError("UA0011_PHOTOS_MISSING")
    return len(photos)


def normalize_ua0011_status() -> dict[str, Any]:
    connection = sqlite3.connect(str(ROOT / "crm.db"), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA busy_timeout=30000")
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            raise InstallError("CRM_QUICK_CHECK:" + str(quick))
        connection.execute("BEGIN IMMEDIATE")
        before = _ua0011_row(connection)
        photo_count = _validate_ua0011_identity(before)
        before_status = str(before.get("status") or "").strip()
        if before_status not in ("kr_bought", "sea_loaded"):
            raise InstallError("UA0011_STATUS_UNEXPECTED:" + before_status)
        changed = before_status == "kr_bought"
        if changed:
            cursor = connection.execute(
                "UPDATE cars SET status = ? WHERE id = ? AND status = ?",
                ("sea_loaded", before["id"], "kr_bought"),
            )
            if cursor.rowcount != 1:
                raise InstallError("UA0011_STATUS_UPDATE_RACE")
        after = _ua0011_row(connection)
        after_status = str(after.get("status") or "").strip()
        fields_changed = sorted(
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        )
        expected = ["status"] if changed else []
        if after_status != "sea_loaded" or fields_changed != expected:
            raise InstallError("UA0011_STATUS_CONTRACT:" + ",".join(fields_changed))
        connection.commit()
        return {
            "target_id": "UA-0011",
            "before_status": before_status,
            "after_status": after_status,
            "changed": changed,
            "fields_changed": fields_changed,
            "photo_count": photo_count,
            "vin4": "4289",
            "before_row_sha256": _row_hash(before),
            "after_row_sha256": _row_hash(after),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def restore_ua0011_status(change: dict[str, Any]) -> dict[str, Any]:
    if not change.get("changed"):
        return {"changed": False, "status": str(change.get("before_status") or "sea_loaded")}
    before_status = str(change.get("before_status") or "")
    after_status = str(change.get("after_status") or "")
    if (before_status, after_status) != ("kr_bought", "sea_loaded"):
        raise InstallError("UA0011_ROLLBACK_CONTRACT_INVALID")
    connection = sqlite3.connect(str(ROOT / "crm.db"), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("BEGIN IMMEDIATE")
        current = _ua0011_row(connection)
        if str(current.get("status") or "").strip() != after_status:
            raise InstallError("UA0011_ROLLBACK_STATUS_RACE")
        cursor = connection.execute(
            "UPDATE cars SET status = ? WHERE id = ? AND status = ?",
            (before_status, current["id"], after_status),
        )
        if cursor.rowcount != 1:
            raise InstallError("UA0011_ROLLBACK_UPDATE_RACE")
        restored = _ua0011_row(connection)
        if str(restored.get("status") or "").strip() != before_status:
            raise InstallError("UA0011_ROLLBACK_VERIFY")
        connection.commit()
        return {"changed": True, "status": before_status}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


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
    snapshot = root / "crm.db.snapshot"
    source = sqlite3.connect(str(ROOT / "crm.db"), timeout=30)
    target = sqlite3.connect(str(snapshot))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    snapshot_data = read(snapshot)
    manifest["__crm_snapshot__"] = {
        "path": str(snapshot), "sha256": sha(snapshot_data), "bytes": len(snapshot_data),
        "restore_mode": "manual_recovery_only",
    }
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
    before_rows, row_count = published_rows_hash()
    before_pages = protected_pages()
    before_media = ua0011_media()
    source = PUBLISHER.read_text(encoding="utf-8")
    publisher_candidate = patch_publisher(source)
    for destination, source_path in SOURCE_INBOX.items():
        payload = read(source_path)
        compile(payload.decode("utf-8"), destination.name, "exec")

    backup_root = create_backup()
    changed = []
    status_change = None
    try:
        status_change = normalize_ua0011_status()
        normalized_rows, normalized_count = published_rows_hash()
        if normalized_count != row_count:
            raise InstallError("CRM_ROW_COUNT_CHANGED")
        if bool(status_change.get("changed")) != (normalized_rows != before_rows):
            raise InstallError("CRM_STATUS_HASH_CONTRACT")

        for destination, source_path in SOURCE_INBOX.items():
            payload = read(source_path)
            if not destination.is_file() or read(destination) != payload:
                atomic(destination, payload, destination.stat().st_mode & 0o777 if destination.exists() else 0o644)
                changed.append(str(destination))
        if publisher_candidate.encode() != read(PUBLISHER):
            atomic(PUBLISHER, publisher_candidate.encode(), PUBLISHER.stat().st_mode & 0o777)
            changed.append(str(PUBLISHER))

        runtime = import_runtime()
        repair = runtime.enforce_live_catalog("UA-0011")
        changed.extend(repair.get("changed_paths") or [])
        after_rows, after_count = published_rows_hash()
        if (after_rows, after_count) != (normalized_rows, row_count):
            raise InstallError("CRM_ROWS_CHANGED_OUTSIDE_STATUS")
        if protected_pages() != before_pages:
            raise InstallError("INDIVIDUAL_PAGES_CHANGED")
        if ua0011_media() != before_media:
            raise InstallError("UA0011_MEDIA_CHANGED")
        postcheck = verify_catalogs(runtime, after_rows)
        return {
            "contract_id": CONTRACT_ID,
            "status": "PASS",
            "mode": "INSTALL",
            "production_write": True,
            "crm_write": bool(status_change.get("changed")),
            "media_write": False,
            "llm_tokens": 0,
            "backup_root": str(backup_root),
            "changed_paths": sorted(set(changed)),
            "published_rows": row_count,
            "rows_sha256_before": before_rows,
            "rows_sha256_after": after_rows,
            "protected_pages": len(before_pages),
            "ua0011_media_files": len(before_media),
            "status_normalization": status_change,
            "repair": repair,
            "postcheck": postcheck,
        }
    except Exception:
        restore(backup_root)
        if status_change and status_change.get("changed"):
            restore_ua0011_status(status_change)
        raise


def run_postcheck() -> dict[str, Any]:
    rows_hash, row_count = published_rows_hash()
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
        "runtime": value,
    }


def run_rollback() -> dict[str, Any]:
    receipt = json.loads(RECEIPTS["install"].read_text(encoding="utf-8"))
    backup_root = pathlib.Path(str(receipt.get("backup_root") or ""))
    status_restored = restore_ua0011_status(receipt.get("status_normalization") or {})
    restored = restore(backup_root)
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_write": bool(status_restored.get("changed")),
        "media_write": False,
        "backup_root": str(backup_root),
        "status_restored": status_restored,
        "restored": restored,
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

