#!/usr/bin/env python3
"""Atomic PythonAnywhere installer for homepage stage counter synchronization."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
from typing import Any


CONTRACT_ID = "UA-HOME-STAGE-COUNTER-SYNC-093-V1.0"
ROOT = pathlib.Path("/home/Carix")
REMOTE = ROOT / "autopilot_inbox/cloud/task_093_home_stage_counter_sync"
GUARD_SOURCE = REMOTE / "home_counter_guard.py"
DB = ROOT / "crm.db"
VIDEO_HOME = ROOT / "video/index.html"
SITE_HOME = ROOT / "site/index.html"
VIDEO_CATALOG = ROOT / "video/katalog.html"
LOCK = ROOT / ".ua_art_production_writer.lock"
BACKUPS = ROOT / "backups/task_093_home_counters"
LAST_SUCCESS = REMOTE / "last_successful_install.json"
RECEIPTS = {mode: REMOTE / ("%s_receipt.json" % mode)
            for mode in ("install", "postcheck", "rollback")}
PUBLIC_HOME = "https://www.uaart.com.ua/video/index.html"
MAX_FILE = 8 * 1024 * 1024


class InstallError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: pathlib.Path) -> bytes:
    value = path.read_bytes()
    if len(value) > MAX_FILE:
        raise InstallError("FILE_TOO_LARGE:" + str(path))
    return value


def atomic(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix="." + path.name + ".", suffix=".task093.tmp",
        delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        0o644,
    )


@contextlib.contextmanager
def production_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_guard():
    specification = importlib.util.spec_from_file_location(
        "task093_home_counter_guard", GUARD_SOURCE)
    if specification is None or specification.loader is None:
        raise InstallError("GUARD_IMPORT")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    if getattr(module, "CONTRACT_ID", None) != CONTRACT_ID:
        raise InstallError("GUARD_CONTRACT")
    return module


def db_snapshot(guard) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    before = read(DB)
    connection = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM cars WHERE published=1 ORDER BY auto_number, id"
            ).fetchall()
        ]
    finally:
        connection.close()
    if quick != "ok":
        raise InstallError("CRM_QUICK_CHECK:" + quick)
    counts = guard.counts_from_rows(rows)
    targets = [
        row for row in rows
        if str(row.get("auto_number") or "").strip().upper() == "UA-0011"
    ]
    if len(targets) != 1 or guard.stage_number(targets[0]) != 2:
        raise InstallError("UA0011_NOT_UNIQUE_FERRY")
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    return rows, {
        "quick_check": quick,
        "file_sha256": sha(before),
        "rows_sha256": sha(normalized),
        "counts": counts,
        "ua0011": {
            "published": targets[0].get("published"),
            "status": targets[0].get("status"),
            "vin": targets[0].get("vin"),
        },
    }


def catalog_snapshot() -> dict[str, Any]:
    source = read(VIDEO_CATALOG).decode("utf-8")
    blocks = re.findall(
        r'<(?:a|article)\b(?=[^>]*\bdata-ua-card\s*=)[^>]*>.*?</(?:a|article)\s*>',
        source, re.I | re.S)
    cards: dict[str, str] = {}
    aliases = {"kiev": "kiev", "kyiv": "kiev", "gruzia": "georgia",
               "georgia": "georgia", "more": "sea", "sea": "sea",
               "korea": "korea"}
    for block in blocks:
        identifier_match = re.search(
            r'\bdata-ua-card\s*=\s*["\'](UA-[0-9]{4,})["\']',
            block, re.I)
        stage_match = re.search(
            r'\bdata-(?:ua-card-stage|etap|stage)\s*=\s*["\']([^"\']+)["\']',
            block, re.I)
        if not identifier_match or not stage_match:
            continue
        identifier = identifier_match.group(1).upper()
        stage = aliases.get(stage_match.group(1).casefold())
        if not stage:
            raise InstallError("CATALOG_UNKNOWN_STAGE:" + identifier)
        if identifier in cards:
            raise InstallError("CATALOG_DUPLICATE:" + identifier)
        cards[identifier] = stage
    counts = {"all": len(cards), "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    for stage in cards.values():
        counts[stage] += 1
    return {"sha256": sha(source.encode()), "cards": cards, "counts": counts}


def public_home() -> bytes:
    request = urllib.request.Request(
        PUBLIC_HOME + "?task093_preimage=" + utc_now().replace(":", ""),
        headers={"User-Agent": "UA-ART-task093/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        value = response.read(MAX_FILE + 1)
    if len(value) > MAX_FILE:
        raise InstallError("PUBLIC_HOME_TOO_LARGE")
    return value


def targets_to_patch(guard, counts: dict[str, int]) -> dict[pathlib.Path, bytes]:
    result: dict[pathlib.Path, bytes] = {}
    for path, required in ((VIDEO_HOME, True), (SITE_HOME, False)):
        if not path.is_file():
            if required:
                raise InstallError("HOME_MISSING:" + str(path))
            continue
        source = read(path).decode("utf-8")
        try:
            candidate = guard.patch_home(source, counts).encode("utf-8")
        except Exception:
            if required:
                raise
            continue
        result[path] = candidate
    if VIDEO_HOME not in result:
        raise InstallError("VIDEO_HOME_NOT_PATCHABLE")
    return result


def verify_targets(guard, counts: dict[str, int], paths: list[pathlib.Path]) -> dict[str, Any]:
    result = {}
    for path in paths:
        source = read(path).decode("utf-8")
        audit = guard.audit_home(source, counts)
        if audit.get("status") != "PASS":
            raise InstallError(
                "HOME_AUDIT:%s:%s" % (path, ",".join(audit.get("errors") or [])))
        result[str(path)] = {
            "sha256": sha(source.encode()),
            "bytes": len(source.encode()),
            "audit": audit,
        }
    return result


def run_install() -> dict[str, Any]:
    guard = load_guard()
    started = utc_now()
    with production_lock():
        rows, database_before = db_snapshot(guard)
        catalog = catalog_snapshot()
        if catalog["counts"] != database_before["counts"]:
            raise InstallError("CRM_CATALOG_COUNT_MISMATCH")
        db_ids = {
            str(row.get("auto_number") or "").strip().upper()
            for row in rows if int(row.get("published") or 0) == 1
        }
        if set(catalog["cards"]) != db_ids:
            raise InstallError("CRM_CATALOG_ID_MISMATCH")
        local_before = read(VIDEO_HOME)
        public_before = public_home()
        if sha(local_before) != sha(public_before):
            raise InstallError("PUBLIC_VIDEO_HOME_PATH_MISMATCH")
        candidates = targets_to_patch(guard, database_before["counts"])
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_root = BACKUPS / (stamp + "_" + sha(local_before)[:10])
        backup_root.mkdir(parents=True, exist_ok=False)
        before: dict[str, Any] = {}
        for path in candidates:
            value = read(path)
            relative = path.relative_to(ROOT)
            destination = backup_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            before[str(path)] = {
                "sha256": sha(value),
                "mode": path.stat().st_mode & 0o777,
                "backup": str(destination),
            }
        changed = []
        try:
            for path, candidate in candidates.items():
                if read(path) != candidate:
                    atomic(path, candidate, before[str(path)]["mode"])
                    changed.append(str(path))
            after = verify_targets(guard, database_before["counts"], list(candidates))
            _, database_after = db_snapshot(guard)
            if database_after["file_sha256"] != database_before["file_sha256"]:
                raise InstallError("CRM_FILE_CHANGED")
            if database_after["rows_sha256"] != database_before["rows_sha256"]:
                raise InstallError("CRM_ROWS_CHANGED")
        except Exception:
            for path_text, metadata in before.items():
                path = pathlib.Path(path_text)
                atomic(path, read(pathlib.Path(metadata["backup"])), int(metadata["mode"]))
            raise
        manifest = {
            "contract_id": CONTRACT_ID,
            "backup_root": str(backup_root),
            "before": before,
            "paths": sorted(str(path) for path in candidates),
            "counts": database_before["counts"],
            "database_before": database_before,
            "catalog": catalog,
            "changed": changed,
            "installed_at_utc": utc_now(),
        }
        atomic_json(LAST_SUCCESS, manifest)
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "ATOMIC_HOME_COUNTER_INSTALL",
        "production_write": True,
        "crm_write": False,
        "media_write": False,
        "database_before": database_before,
        "database_after": database_after,
        "catalog": catalog,
        "backup_root": str(backup_root),
        "changed_files": changed,
        "targets": after,
        "public_preimage_sha256": sha(public_before),
        "runtime_llm_tokens": 0,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def run_postcheck() -> dict[str, Any]:
    guard = load_guard()
    with production_lock():
        if not LAST_SUCCESS.is_file():
            raise InstallError("LAST_SUCCESS_MISSING")
        manifest = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        rows, database = db_snapshot(guard)
        counts = database["counts"]
        catalog = catalog_snapshot()
        if counts != manifest.get("counts"):
            raise InstallError("POSTCHECK_CRM_DRIFT")
        if catalog["counts"] != counts:
            raise InstallError("POSTCHECK_CATALOG_DRIFT")
        targets = verify_targets(
            guard, counts, [pathlib.Path(value) for value in manifest["paths"]])
        if database["file_sha256"] != manifest["database_before"]["file_sha256"]:
            raise InstallError("POSTCHECK_CRM_FILE_CHANGED")
        if database["rows_sha256"] != manifest["database_before"]["rows_sha256"]:
            raise InstallError("POSTCHECK_CRM_ROWS_CHANGED")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "READ_ONLY_POSTCHECK",
        "production_write": False,
        "crm_write": False,
        "counts": counts,
        "catalog": catalog,
        "targets": targets,
        "runtime_llm_tokens": 0,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def run_rollback() -> dict[str, Any]:
    with production_lock():
        if not LAST_SUCCESS.is_file():
            raise InstallError("ROLLBACK_MANIFEST_MISSING")
        manifest = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        restored = []
        for path_text, metadata in manifest["before"].items():
            path = pathlib.Path(path_text)
            backup = pathlib.Path(metadata["backup"])
            if not str(backup).startswith(str(BACKUPS) + os.sep):
                raise InstallError("ROLLBACK_BACKUP_SCOPE")
            value = read(backup)
            if sha(value) != metadata["sha256"]:
                raise InstallError("ROLLBACK_BACKUP_SHA:" + path_text)
            atomic(path, value, int(metadata["mode"]))
            if sha(read(path)) != metadata["sha256"]:
                raise InstallError("ROLLBACK_READBACK:" + path_text)
            restored.append(path_text)
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_write": False,
        "restored": restored,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=tuple(RECEIPTS))
    args = parser.parse_args()
    try:
        value = {
            "install": run_install,
            "postcheck": run_postcheck,
            "rollback": run_rollback,
        }[args.mode]()
    except Exception as exc:
        value = {
            "contract_id": CONTRACT_ID,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_write": False,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "finished_at_utc": utc_now(),
        }
    atomic_json(RECEIPTS[args.mode], value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
