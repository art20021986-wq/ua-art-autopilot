#!/usr/bin/env python3
"""Fail-closed, code-only installer/rollback for TASK 072 Gate B."""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
from typing import Any


CONTRACT = "CRM-DESCRIPTION-SAVE-072-V2"
EXPECTED_LIVE_CARS_SHA256 = "862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b"
EXPECTED_PATCHED_CARS_SHA256 = "1f5368ea3caeeecb2d55b18b41cb414092495ef2185f7e881767015f53d8634b"
EXPECTED_WRITER_SHA256 = "f85c9a332ad69ac5834d0bf78a23d86a28ea361fba4b9eeef695197784551623"

ROOT = pathlib.Path(os.environ.get("TASK072_ROOT", "/home/Carix"))
SAFE = pathlib.Path(os.environ.get(
    "TASK072_SAFE", "/home/Carix/autopilot_inbox/cloud/task_072"
))


def _set_paths(root: pathlib.Path, safe: pathlib.Path) -> None:
    global ROOT, SAFE, CARS_UI, WRITER, DATABASE, QUEUE, LOCK_FILE
    global CANDIDATE_WRITER, PATCHER, BACKUP_PARENT
    global SHADOW_RECEIPT, INSTALL_RECEIPT, ROLLBACK_RECEIPT
    ROOT = pathlib.Path(root)
    SAFE = pathlib.Path(safe)
    CARS_UI = ROOT / "cars_ui.py"
    WRITER = ROOT / "crm_description_writer.py"
    DATABASE = ROOT / "crm.db"
    QUEUE = pathlib.Path(str(DATABASE) + ".description_queue.sqlite3")
    LOCK_FILE = ROOT / ".task072-description-deploy.lock"
    CANDIDATE_WRITER = SAFE / "crm_description_writer_v2.py"
    PATCHER = SAFE / "patch_cars_ui_v2.py"
    BACKUP_PARENT = SAFE / "backups"
    SHADOW_RECEIPT = SAFE / "shadow_receipt_v2.json"
    INSTALL_RECEIPT = SAFE / "install_receipt_v2.json"
    ROLLBACK_RECEIPT = SAFE / "rollback_receipt_v2.json"


_set_paths(ROOT, SAFE)


class InstallBlocked(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: Any, code: str) -> None:
    if not condition:
        raise InstallBlocked(code)


def read_bytes(path: pathlib.Path, limit: int = 8_000_000) -> bytes:
    data = path.read_bytes()
    require(len(data) <= limit, "FILE_TOO_LARGE:" + path.name)
    return data


def atomic_write(path: pathlib.Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix="." + path.name + ".",
        suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def import_path(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise InstallBlocked("MODULE_LOAD:" + path.name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row_hash(row: sqlite3.Row) -> str:
    payload = {key: row[key] for key in sorted(row.keys())}
    return sha(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode())


def database_snapshot() -> dict[str, Any]:
    uri = "file:%s?mode=ro" % DATABASE.as_posix()
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        count = int(conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0])
        ua0009 = list(conn.execute("SELECT * FROM cars WHERE auto_number='UA-0009'"))
        require(quick == "ok", "DATABASE_QUICK_CHECK")
        require(count == 11, "DATABASE_CARD_COUNT")
        require(len(ua0009) == 1, "UA0009_NOT_UNIQUE")
        return {
            "quick_check": quick,
            "cards_count": count,
            "ua0009_rows": 1,
            "ua0009_sha256": row_hash(ua0009[0]),
            "database_sha256": sha(read_bytes(DATABASE, 50_000_000)),
        }
    finally:
        conn.close()


def candidate() -> dict[str, Any]:
    patcher = import_path(PATCHER, "task072_installer_patcher")
    live = read_bytes(CARS_UI)
    current_sha = sha(live)
    writer = read_bytes(CANDIDATE_WRITER)
    require(sha(writer) == EXPECTED_WRITER_SHA256, "WRITER_RELEASE_SHA")
    compile(writer.decode("utf-8"), "crm_description_writer.py", "exec")
    if current_sha == EXPECTED_PATCHED_CARS_SHA256:
        require(WRITER.exists(), "PATCHED_WITHOUT_WRITER")
        require(sha(read_bytes(WRITER)) == EXPECTED_WRITER_SHA256,
                "PATCHED_WRITER_SHA")
        patched = live
        already_installed = True
    else:
        require(current_sha == EXPECTED_LIVE_CARS_SHA256, "LIVE_CARS_SHA_DRIFT")
        patched = patcher.patch_source(live)
        require(sha(patched) == EXPECTED_PATCHED_CARS_SHA256, "PATCHED_CARS_SHA")
        already_installed = False
    compile(patched.decode("utf-8"), "cars_ui.py", "exec")
    return {
        "live_cars_sha256": current_sha,
        "patched_cars_sha256": sha(patched),
        "writer_sha256": sha(writer),
        "already_installed": already_installed,
        "patched_bytes": patched,
        "writer_bytes": writer,
    }


def queue_snapshot() -> dict[str, Any]:
    if not QUEUE.exists():
        return {"exists": False, "sha256": None, "size_bytes": 0}
    data = read_bytes(QUEUE, 50_000_000)
    return {"exists": True, "sha256": sha(data), "size_bytes": len(data)}


@contextlib.contextmanager
def deployment_lock():
    ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def shadow() -> dict[str, Any]:
    release = candidate()
    database = database_snapshot()
    queue = queue_snapshot()
    return {
        "contract_id": CONTRACT,
        "mode": "SHADOW",
        "status": "PASS",
        "production_write": False,
        "crm_db_write": False,
        "runtime_llm_tokens": 0,
        "candidate": {key: value for key, value in release.items() if not key.endswith("bytes")},
        "database": database,
        "queue": queue,
        "created_at_utc": utc_now(),
    }


def make_backup(release: dict[str, Any], database: dict[str, Any]) -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_PARENT / stamp
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = BACKUP_PARENT / (stamp + "-%d" % suffix)
    backup.mkdir(parents=True, mode=0o700)
    cars_data = read_bytes(CARS_UI)
    atomic_write(backup / "cars_ui.py", cars_data, CARS_UI.stat().st_mode & 0o777)
    writer_existed = WRITER.exists()
    if writer_existed:
        atomic_write(
            backup / "crm_description_writer.py",
            read_bytes(WRITER),
            WRITER.stat().st_mode & 0o777,
        )
    manifest = {
        "contract_id": CONTRACT,
        "created_at_utc": utc_now(),
        "cars_ui_sha256": sha(cars_data),
        "cars_ui_mode": CARS_UI.stat().st_mode & 0o777,
        "writer_existed": writer_existed,
        "writer_sha256": sha(read_bytes(WRITER)) if writer_existed else None,
        "writer_mode": (WRITER.stat().st_mode & 0o777) if writer_existed else None,
        "database": database,
        "queue_before": queue_snapshot(),
        "release": {key: value for key, value in release.items() if not key.endswith("bytes")},
    }
    atomic_json(backup / "manifest.json", manifest)
    return backup


def rollback_backup(backup: pathlib.Path) -> dict[str, Any]:
    resolved = backup.resolve()
    require(BACKUP_PARENT.resolve() in resolved.parents, "ROLLBACK_BACKUP_SCOPE")
    manifest = json.loads(read_bytes(resolved / "manifest.json", 2_000_000).decode())
    require(manifest.get("contract_id") == CONTRACT, "ROLLBACK_MANIFEST_CONTRACT")
    queue_before = queue_snapshot()
    original_cars = read_bytes(resolved / "cars_ui.py")
    atomic_write(CARS_UI, original_cars, int(manifest.get("cars_ui_mode") or 0o644))
    if manifest.get("writer_existed"):
        atomic_write(
            WRITER,
            read_bytes(resolved / "crm_description_writer.py"),
            int(manifest.get("writer_mode") or 0o644),
        )
    elif WRITER.exists():
        WRITER.unlink()
    compile(read_bytes(CARS_UI).decode("utf-8"), "cars_ui.py", "exec")
    queue_after = queue_snapshot()
    require(sha(read_bytes(CARS_UI)) == manifest["cars_ui_sha256"],
            "ROLLBACK_CARS_SHA")
    if manifest.get("writer_existed"):
        require(sha(read_bytes(WRITER)) == manifest["writer_sha256"],
                "ROLLBACK_WRITER_SHA")
    else:
        require(not WRITER.exists(), "ROLLBACK_WRITER_PRESENT")
    after_db = database_snapshot()
    return {
        "contract_id": CONTRACT,
        "mode": "ROLLBACK",
        "status": "PASS",
        "production_write": True,
        "crm_db_write": False,
        "backup_root": str(resolved),
        "queue_preserved": True,
        "queue_observed_before": queue_before,
        "queue_observed_after": queue_after,
        "database_restored_from_backup": False,
        "database_after": after_db,
        "runtime_llm_tokens": 0,
    }


def install() -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "contract_id": CONTRACT,
        "mode": "INSTALL",
        "status": "BLOCKED",
        "production_write": False,
        "crm_db_write": False,
        "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(),
        "errors": [],
        "rollback": None,
    }
    backup: pathlib.Path | None = None
    try:
        with deployment_lock():
            release = candidate()
            database_before = database_snapshot()
            queue_before = queue_snapshot()
            receipt["database_before"] = database_before
            receipt["queue_before"] = queue_before
            receipt["candidate"] = {
                key: value for key, value in release.items() if not key.endswith("bytes")
            }
            if release["already_installed"]:
                receipt["already_installed"] = True
            else:
                backup = make_backup(release, database_before)
                receipt["backup_root"] = str(backup)
                # Install the dependency first; cars_ui imports it lazily only
                # after its own atomic replacement and the controlled restart.
                atomic_write(WRITER, release["writer_bytes"], 0o644)
                receipt["production_write"] = True
                atomic_write(
                    CARS_UI,
                    release["patched_bytes"],
                    CARS_UI.stat().st_mode & 0o777,
                )
            require(sha(read_bytes(WRITER)) == EXPECTED_WRITER_SHA256,
                    "INSTALL_WRITER_READBACK")
            require(sha(read_bytes(CARS_UI)) == EXPECTED_PATCHED_CARS_SHA256,
                    "INSTALL_CARS_READBACK")
            compile(read_bytes(WRITER).decode("utf-8"), "crm_description_writer.py", "exec")
            compile(read_bytes(CARS_UI).decode("utf-8"), "cars_ui.py", "exec")
            database_after = database_snapshot()
            queue_after = queue_snapshot()
            require(database_after == database_before, "INSTALL_DATABASE_CHANGED")
            require(queue_after == queue_before, "INSTALL_QUEUE_CHANGED")
            receipt["database_after"] = database_after
            receipt["queue_after"] = queue_after
            receipt["queue_preserved"] = True
            receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if backup is not None and receipt["production_write"]:
            try:
                receipt["rollback"] = rollback_backup(backup)
                receipt["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                receipt["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                receipt["status"] = "BLOCKED"
    receipt["finished_at_utc"] = utc_now()
    return receipt


def explicit_rollback() -> dict[str, Any]:
    install_receipt = json.loads(read_bytes(INSTALL_RECEIPT, 2_000_000).decode())
    require(install_receipt.get("contract_id") == CONTRACT, "INSTALL_RECEIPT_CONTRACT")
    backup = pathlib.Path(str(install_receipt.get("backup_root") or ""))
    require(str(backup), "INSTALL_RECEIPT_BACKUP")
    with deployment_lock():
        return rollback_backup(backup)


def main() -> int:
    SAFE.mkdir(parents=True, exist_ok=True)
    if "--shadow" in sys.argv:
        output = SHADOW_RECEIPT
        try:
            value = shadow()
        except Exception as exc:
            value = {
                "contract_id": CONTRACT,
                "mode": "SHADOW",
                "status": "BLOCKED",
                "production_write": False,
                "crm_db_write": False,
                "runtime_llm_tokens": 0,
                "errors": [type(exc).__name__ + ":" + str(exc)],
            }
    elif "--rollback" in sys.argv:
        output = ROLLBACK_RECEIPT
        try:
            value = explicit_rollback()
        except Exception as exc:
            value = {
                "contract_id": CONTRACT,
                "mode": "ROLLBACK",
                "status": "BLOCKED",
                "crm_db_write": False,
                "runtime_llm_tokens": 0,
                "errors": [type(exc).__name__ + ":" + str(exc)],
            }
    else:
        output = INSTALL_RECEIPT
        value = install()
    atomic_json(output, value)
    print(json.dumps({"status": value.get("status"), "mode": value.get("mode")}, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
