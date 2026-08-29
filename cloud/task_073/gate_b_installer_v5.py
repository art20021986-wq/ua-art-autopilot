#!/usr/bin/env python3
"""Remote fail-closed installer/rollback for TASK 073 V5.

This file runs on PythonAnywhere only after the exact owner-approved Gate B
controller has completed a live shadow.  It never restores crm.db; the
database is read-only and any observed change blocks the release.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Dict

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import patcher_v5 as patcher


CONTRACT = "CRM-UNIFIED-CATALOG-001-V1.0"
ROOT = pathlib.Path(os.environ.get("TASK073_ROOT", "/home/Carix"))
SAFE = pathlib.Path(os.environ.get(
    "TASK073_SAFE", "/home/Carix/autopilot_inbox/cloud/task_073"
))
BACKUP_PARENT = SAFE / "backups_v5"
LOCK_FILE = SAFE / ".task073-v5.lock"
DATABASE = ROOT / "crm.db"
TARGET = "UA-0011"
PUBLIC_DIRS = (ROOT / "video", ROOT / "site")
SHADOW_RECEIPT = SAFE / "shadow_receipt_v5.json"
INSTALL_RECEIPT = SAFE / "install_receipt_v5.json"
ROLLBACK_RECEIPT = SAFE / "rollback_receipt_v5.json"


class InstallBlocked(RuntimeError):
    pass


def require(condition: Any, code: str) -> None:
    if not condition:
        raise InstallBlocked(code)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_bytes(path: pathlib.Path, limit: int = 50_000_000) -> bytes:
    value = path.read_bytes()
    require(len(value) <= limit, "FILE_TOO_LARGE:" + path.name)
    return value


def atomic_write(path: pathlib.Path, value: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix="." + path.name + ".",
        suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict) -> None:
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


@contextlib.contextmanager
def deployment_lock():
    SAFE.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def row_hash(row: sqlite3.Row) -> str:
    payload = {name: row[name] for name in sorted(row.keys())}
    return sha_bytes(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=str
    ).encode())


def database_snapshot() -> dict:
    uri = "file:%s?mode=ro" % DATABASE.as_posix()
    connection = sqlite3.connect(uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        rows = list(connection.execute("SELECT * FROM cars ORDER BY id"))
        numbers = [str(row["auto_number"] or "") for row in rows]
        require(quick == "ok", "DATABASE_QUICK_CHECK")
        require(len(rows) == 11, "DATABASE_CARD_COUNT:%d" % len(rows))
        require(len(set(numbers)) == 11 and TARGET in numbers, "DATABASE_CARD_IDENTITIES")
        hashes = {str(row["auto_number"]): row_hash(row) for row in rows}
        require(
            hashes.get("UA-0009")
            == "b31572a4d321e40a8f8d07b7b127db4751f1cdaa8a1aa2369e27754f178dfbf7",
            "UA0009_ROW_SHA",
        )
        return {
            "quick_check": quick,
            "cards_count": len(rows),
            "unique_auto_numbers": True,
            "row_sha256": hashes,
            "database_sha256": sha_bytes(read_bytes(DATABASE)),
        }
    finally:
        connection.close()


def protected_pages_snapshot() -> Dict[str, str]:
    output = {}
    for directory in PUBLIC_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("UA-*.html")):
            if path.name.startswith(TARGET):
                continue
            output[str(path)] = sha_bytes(read_bytes(path, 5_000_000))
    return output


def public_targets():
    paths = []
    for directory in PUBLIC_DIRS:
        paths.extend([
            directory / (TARGET + ".html"),
            directory / (TARGET + "-diag.html"),
            directory / "katalog.html",
        ])
        if directory.is_dir():
            paths.extend(sorted(directory.glob(TARGET + "-[0-9a-f]*.html")))
    return sorted(set(paths), key=str)


def file_state(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"exists": False, "sha256": None, "size": 0}
    value = read_bytes(path, 8_000_000)
    return {"exists": True, "sha256": sha_bytes(value), "size": len(value)}


def target_snapshot() -> Dict[str, dict]:
    return {str(path): file_state(path) for path in public_targets()}


def code_snapshot() -> Dict[str, str]:
    return {
        name: sha_bytes(read_bytes(ROOT / name, 8_000_000))
        for name in patcher.FULL_FILE_SHA256
    }


def full_snapshot() -> dict:
    return {
        "code_sha256": code_snapshot(),
        "database": database_snapshot(),
        "protected_pages_sha256": protected_pages_snapshot(),
        "target_state": target_snapshot(),
    }


def build_candidates() -> Dict[str, bytes]:
    sources = {
        name: read_bytes(ROOT / name, 8_000_000).decode("utf-8")
        for name in patcher.FULL_FILE_SHA256
    }
    values = patcher.build_candidates(sources, check_full_sha=True)
    return {name: value.encode("utf-8") for name, value in values.items()}


def parse_marker(stdout: str) -> dict:
    marker = "TASK073_RESULT="
    values = [line[len(marker):] for line in stdout.splitlines() if line.startswith(marker)]
    require(len(values) == 1, "PUBLISH_RESULT_MARKER:%d" % len(values))
    return json.loads(values[0])


def run_publisher(proba: bool, candidate_dir: pathlib.Path | None = None) -> dict:
    script = (
        "import json,publikaciya;"
        "ok,msg=publikaciya.opublikovat('UA-0011',proba=%s);"
        "print('TASK073_RESULT='+json.dumps({'ok':ok,'message':msg},ensure_ascii=False))"
        % ("True" if proba else "False")
    )
    environment = os.environ.copy()
    if candidate_dir is not None:
        environment["PYTHONPATH"] = str(candidate_dir) + os.pathsep + str(ROOT)
        working = candidate_dir
    else:
        environment["PYTHONPATH"] = str(ROOT)
        working = ROOT
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=str(working), env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=420,
    )
    value = parse_marker(completed.stdout)
    value["returncode"] = completed.returncode
    value["stderr_tail"] = completed.stderr[-2000:]
    require(completed.returncode == 0, "PUBLISH_SUBPROCESS:%d" % completed.returncode)
    require(value.get("ok") is True, "PUBLISH_FALSE:" + str(value.get("message")))
    return value


def validate_local_public() -> dict:
    output = {}
    href = re.compile(r"href=['\"]UA\-0011\.html(?:[?#][^'\"]*)?['\"]")
    diag_href = re.compile(r"href=['\"]UA\-0011\-diag\.html(?:[?#][^'\"]*)?['\"]")
    for directory in PUBLIC_DIRS:
        require(directory.is_dir(), "PUBLIC_DIR_MISSING:" + str(directory))
        primary = (directory / (TARGET + ".html")).read_text(encoding="utf-8")
        diag = (directory / (TARGET + "-diag.html")).read_text(encoding="utf-8")
        catalog = (directory / "katalog.html").read_text(encoding="utf-8")
        require(TARGET in primary and len(diag_href.findall(primary)) == 1,
                "PRIMARY_LOCAL:" + str(directory))
        require(TARGET in diag and "иагност" in diag.lower(),
                "DIAG_LOCAL:" + str(directory))
        require(len(href.findall(catalog)) == 1, "CATALOG_LOCAL:" + str(directory))
        output[str(directory)] = {
            "primary_sha256": sha_bytes(primary.encode()),
            "diag_sha256": sha_bytes(diag.encode()),
            "catalog_sha256": sha_bytes(catalog.encode()),
            "catalog_href_count": 1,
        }
    return output


def make_backup(before: dict) -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_PARENT / stamp
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = BACKUP_PARENT / (stamp + "-%d" % suffix)
    backup.mkdir(parents=True, mode=0o700)
    entries = {}
    paths = [ROOT / name for name in patcher.FULL_FILE_SHA256] + public_targets()
    for path in paths:
        state = file_state(path)
        key = str(path)
        entry = dict(state)
        entry["mode"] = (path.stat().st_mode & 0o777) if path.exists() else None
        entry["backup_name"] = None
        if path.exists():
            name = hashlib.sha256(key.encode()).hexdigest() + ".bak"
            shutil.copy2(path, backup / name)
            require(sha_bytes(read_bytes(backup / name, 8_000_000)) == state["sha256"],
                    "BACKUP_SHA:" + key)
            entry["backup_name"] = name
        entries[key] = entry
    manifest = {
        "contract_id": CONTRACT,
        "created_at_utc": utc_now(),
        "entries": entries,
        "before": before,
    }
    atomic_json(backup / "manifest.json", manifest)
    return backup


def restore_backup(backup: pathlib.Path) -> dict:
    resolved = backup.resolve()
    require(BACKUP_PARENT.resolve() in resolved.parents, "BACKUP_SCOPE")
    manifest = json.loads(read_bytes(resolved / "manifest.json", 3_000_000).decode())
    require(manifest.get("contract_id") == CONTRACT, "BACKUP_CONTRACT")
    for key, entry in manifest["entries"].items():
        path = pathlib.Path(key)
        if entry["exists"]:
            value = read_bytes(resolved / entry["backup_name"], 8_000_000)
            atomic_write(path, value, int(entry.get("mode") or 0o644))
        elif path.exists():
            path.unlink()
    for key, entry in manifest["entries"].items():
        require(file_state(pathlib.Path(key)) == {
            "exists": entry["exists"], "sha256": entry["sha256"], "size": entry["size"]
        }, "ROLLBACK_TARGET:" + key)
    after = full_snapshot()
    before = manifest["before"]
    require(after["code_sha256"] == before["code_sha256"], "ROLLBACK_CODE")
    require(after["database"] == before["database"], "ROLLBACK_DATABASE_EXTERNAL_CHANGE")
    require(after["protected_pages_sha256"] == before["protected_pages_sha256"],
            "ROLLBACK_PROTECTED")
    return {"backup_root": str(resolved), "verified": True, "after": after}


def shadow() -> dict:
    receipt = {
        "contract_id": CONTRACT, "mode": "SHADOW", "status": "BLOCKED",
        "production_write": False, "crm_db_write": False,
        "runtime_llm_tokens": 0, "started_at_utc": utc_now(), "errors": [],
    }
    temporary = None
    try:
        with deployment_lock():
            before = full_snapshot()
            candidates = build_candidates()
            temporary = pathlib.Path(tempfile.mkdtemp(prefix="task073_shadow_", dir=SAFE))
            for name, value in candidates.items():
                atomic_write(temporary / name, value)
            receipt["publisher_probe"] = run_publisher(True, temporary)
            after = full_snapshot()
            require(after == before, "SHADOW_CHANGED_PRODUCTION")
            receipt["before"] = before
            receipt["candidate_sha256"] = {
                name: sha_bytes(value) for name, value in candidates.items()
            }
            receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
    receipt["finished_at_utc"] = utc_now()
    return receipt


def install() -> dict:
    receipt = {
        "contract_id": CONTRACT, "mode": "INSTALL", "status": "BLOCKED",
        "production_write": False, "crm_db_write": False,
        "runtime_llm_tokens": 0, "started_at_utc": utc_now(), "errors": [],
        "rollback": None,
    }
    backup = None
    try:
        with deployment_lock():
            before = full_snapshot()
            candidates = build_candidates()
            backup = make_backup(before)
            receipt["backup_root"] = str(backup)
            receipt["before"] = before
            receipt["candidate_sha256"] = {
                name: sha_bytes(value) for name, value in candidates.items()
            }
            for name, value in candidates.items():
                atomic_write(ROOT / name, value, (ROOT / name).stat().st_mode & 0o777)
            receipt["production_write"] = True
            for name, expected in receipt["candidate_sha256"].items():
                require(sha_bytes(read_bytes(ROOT / name, 8_000_000)) == expected,
                        "INSTALL_CODE_READBACK:" + name)
            receipt["publisher"] = run_publisher(False)
            after = full_snapshot()
            require(after["database"] == before["database"], "INSTALL_DATABASE_CHANGED")
            require(after["protected_pages_sha256"] == before["protected_pages_sha256"],
                    "INSTALL_PROTECTED_CHANGED")
            require(after["code_sha256"] == receipt["candidate_sha256"],
                    "INSTALL_CODE_CHANGED")
            receipt["local_public"] = validate_local_public()
            receipt["after"] = after
            receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if backup is not None and receipt["production_write"]:
            try:
                receipt["rollback"] = restore_backup(backup)
                receipt["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                receipt["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                receipt["status"] = "BLOCKED"
    receipt["finished_at_utc"] = utc_now()
    return receipt


def explicit_rollback() -> dict:
    install_receipt = json.loads(read_bytes(INSTALL_RECEIPT, 5_000_000).decode())
    require(install_receipt.get("contract_id") == CONTRACT, "INSTALL_RECEIPT_CONTRACT")
    backup = pathlib.Path(str(install_receipt.get("backup_root") or ""))
    require(bool(str(backup)), "INSTALL_RECEIPT_BACKUP")
    with deployment_lock():
        details = restore_backup(backup)
    return {
        "contract_id": CONTRACT, "mode": "ROLLBACK", "status": "PASS",
        "production_write": True, "crm_db_write": False,
        "runtime_llm_tokens": 0, **details,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--shadow", action="store_true")
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    SAFE.mkdir(parents=True, exist_ok=True)
    if args.shadow:
        value, output = shadow(), SHADOW_RECEIPT
    elif args.install:
        value, output = install(), INSTALL_RECEIPT
    else:
        try:
            value = explicit_rollback()
        except Exception as exc:
            value = {
                "contract_id": CONTRACT, "mode": "ROLLBACK", "status": "BLOCKED",
                "errors": [type(exc).__name__ + ":" + str(exc)],
            }
        output = ROLLBACK_RECEIPT
    atomic_json(output, value)
    print(json.dumps({"status": value.get("status"), "errors": value.get("errors", [])},
                     ensure_ascii=False))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
