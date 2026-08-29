#!/usr/bin/env python3
"""Remote atomic installer/rollback for CRM-VIN4-TITLE-001 v1.0."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import time

ROOT = pathlib.Path(os.environ.get("TASK082_ROOT", "/home/Carix"))
UPLOADS = ROOT / "uploads"
SOURCE = ROOT / "cars_ui.py"
DB = ROOT / "crm.db"
CONFIG = UPLOADS / "task082_install_config.json"
CANDIDATE = UPLOADS / "task082_cars_ui_candidate.py"
RECEIPT = UPLOADS / "task082_install_receipt.json"
BACKUPS = ROOT / "autopilot_inbox" / "cloud" / "task_082_vin4_title" / "backups"
LOCK = ROOT / ".task082_vin4_title.lock"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: pathlib.Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    temporary = pathlib.Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory_fd = os.open(str(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _db_state() -> dict:
    data = DB.read_bytes()
    uri = "file:%s?mode=ro" % DB
    connection = sqlite3.connect(uri, uri=True, timeout=20)
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        connection.close()
    return {"sha256": _sha(data), "bytes": len(data), "quick_check": quick}


def _safe_backup(path_value: str) -> pathlib.Path:
    path = pathlib.Path(path_value).resolve()
    root = BACKUPS.resolve()
    if path.parent != root or not path.name.startswith("cars_ui.py.") or not path.name.endswith(".bak"):
        raise RuntimeError("BACKUP_PATH_SCOPE")
    return path


def _receipt(value: dict) -> None:
    value["written_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_write(RECEIPT, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def run() -> int:
    result = {"contract": "CRM-VIN4-TITLE-001-V1.0", "status": "FAIL", "production_touched": False}
    original = None
    original_mode = 0o600
    installed = False
    with open(LOCK, "a+b") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            action = config.get("action")
            if action == "install":
                original = SOURCE.read_bytes()
                original_mode = SOURCE.stat().st_mode & 0o777
                if _sha(original) != config.get("expected_source_sha_before"):
                    raise RuntimeError("SOURCE_SHA_DRIFT")
                candidate = CANDIDATE.read_bytes()
                if _sha(candidate) != config.get("expected_source_sha_after"):
                    raise RuntimeError("CANDIDATE_SHA_MISMATCH")
                compile(candidate.decode("utf-8"), str(SOURCE), "exec")

                before_db = _db_state()
                if before_db["quick_check"] != "ok":
                    raise RuntimeError("DB_QUICK_CHECK_BEFORE")
                BACKUPS.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                backup = BACKUPS / ("cars_ui.py.%s.%s.bak" % (stamp, _sha(original)[:12]))
                _atomic_write(backup, original, original_mode)
                if backup.read_bytes() != original:
                    raise RuntimeError("BACKUP_READBACK")

                _atomic_write(SOURCE, candidate, original_mode)
                installed = True
                after = SOURCE.read_bytes()
                after_db = _db_state()
                if _sha(after) != config.get("expected_source_sha_after"):
                    raise RuntimeError("SOURCE_READBACK")
                if after_db != before_db:
                    raise RuntimeError("DB_CHANGED_DURING_ATOMIC_INSTALL")
                result.update({
                    "status": "PASS",
                    "production_touched": True,
                    "action": "install",
                    "backup_path": str(backup),
                    "source_sha_before": _sha(original),
                    "source_sha_after": _sha(after),
                    "db_before": before_db,
                    "db_after": after_db,
                })
            elif action == "rollback":
                backup = _safe_backup(str(config.get("backup_path") or ""))
                current = SOURCE.read_bytes()
                expected_current = config.get("expected_current_sha")
                if expected_current and _sha(current) != expected_current:
                    raise RuntimeError("ROLLBACK_CURRENT_SHA_DRIFT")
                restored = backup.read_bytes()
                if _sha(restored) != config.get("expected_restored_sha"):
                    raise RuntimeError("ROLLBACK_BACKUP_SHA")
                compile(restored.decode("utf-8"), str(SOURCE), "exec")
                mode = SOURCE.stat().st_mode & 0o777
                _atomic_write(SOURCE, restored, mode)
                if _sha(SOURCE.read_bytes()) != _sha(restored):
                    raise RuntimeError("ROLLBACK_READBACK")
                result.update({
                    "status": "PASS", "production_touched": True, "action": "rollback",
                    "backup_path": str(backup), "restored_sha": _sha(restored),
                })
            else:
                raise RuntimeError("ACTION_INVALID")
        except Exception as exc:
            if installed and original is not None:
                try:
                    _atomic_write(SOURCE, original, original_mode)
                    result["automatic_restore"] = _sha(SOURCE.read_bytes()) == _sha(original)
                except Exception as restore_exc:
                    result["automatic_restore_error"] = type(restore_exc).__name__ + ":" + str(restore_exc)
            result["errors"] = [type(exc).__name__ + ":" + str(exc)]
        finally:
            _receipt(result)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="task082-installer-") as raw:
        path = pathlib.Path(raw) / "nested" / "value.txt"
        _atomic_write(path, b"one", 0o600)
        assert path.read_bytes() == b"one"
        _atomic_write(path, b"two", 0o640)
        assert path.read_bytes() == b"two"
        assert path.stat().st_mode & 0o777 == 0o640


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        print("TASK082_REMOTE_INSTALLER_SELF_TEST_PASS")
        raise SystemExit(0)
    raise SystemExit(run())
