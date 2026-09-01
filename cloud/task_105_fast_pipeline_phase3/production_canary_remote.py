#!/usr/bin/env python3
"""Atomic remote executor for TASK105 FAST production canary.

The only permitted production target is a dedicated static marker file. Existing
site pages, CRM data, media, application code, Cloudflare and DNS are never
written. Every install captures a restorable preimage and rolls back locally on
any failed invariant.
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
import shutil
import tempfile
import uuid
from typing import Any

CONTRACT_ID = "UA-ART-FAST-PRODUCTION-CANARY-105-V1.0"
ROOT = pathlib.Path("/home/Carix")
REMOTE = ROOT / "autopilot_inbox/cloud/task_105_fast_pipeline_phase3"
PAYLOAD = REMOTE / "task105_fast_canary_payload.txt"
TARGET = ROOT / "video/task105-fast-canary.txt"
LOCK = ROOT / ".ua_art_production_writer.lock"
BACKUPS = ROOT / "backups/task_105_fast_canary"
LAST_SUCCESS = REMOTE / "task105_fast_canary_last_success.json"
RECEIPTS = {
    "install": REMOTE / "task105_fast_canary_install_receipt.json",
    "rollback": REMOTE / "task105_fast_canary_rollback_receipt.json",
}
PROTECTED = (
    ROOT / "crm.db",
    ROOT / "video/index.html",
    ROOT / "video/katalog.html",
)
MAX_MARKER_BYTES = 16 * 1024
MAX_PROTECTED_BYTES = 256 * 1024 * 1024


class CanaryError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: pathlib.Path, max_bytes: int = MAX_PROTECTED_BYTES) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise CanaryError("NOT_REGULAR_FILE:" + str(path))
    total = 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise CanaryError("FILE_TOO_LARGE:" + str(path))
            digest.update(chunk)
    return digest.hexdigest(), total


def read_small(path: pathlib.Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CanaryError("NOT_REGULAR_FILE:" + str(path))
    value = path.read_bytes()
    if len(value) > MAX_MARKER_BYTES:
        raise CanaryError("MARKER_TOO_LARGE:" + str(path))
    return value


def fsync_dir(path: pathlib.Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: pathlib.Path, value: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise CanaryError("TARGET_PARENT_SYMLINK")
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".task105.tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write(path, encoded, 0o644)


@contextlib.contextmanager
def production_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def assert_scope() -> None:
    expected = ROOT / "video/task105-fast-canary.txt"
    if TARGET != expected:
        raise CanaryError("TARGET_SCOPE_CHANGED")
    if TARGET.parent.resolve(strict=True) != (ROOT / "video").resolve(strict=True):
        raise CanaryError("TARGET_PARENT_SCOPE")
    if TARGET.is_symlink():
        raise CanaryError("TARGET_SYMLINK")
    if BACKUPS.resolve(strict=False) != (ROOT / "backups/task_105_fast_canary").resolve(strict=False):
        raise CanaryError("BACKUP_SCOPE_CHANGED")


def payload_bytes() -> bytes:
    value = read_small(PAYLOAD)
    if not value.endswith(b"\n"):
        raise CanaryError("PAYLOAD_MISSING_FINAL_NEWLINE")
    text = value.decode("utf-8")
    required = (
        "UA_ART_FAST_PIPELINE_CANARY\n",
        "TASK_ID=TASK105-FAST-PRODUCTION-CANARY\n",
        "CONTRACT_ID=" + CONTRACT_ID + "\n",
        "NO_CRM_WRITE=TRUE\n",
        "NO_EXISTING_SITE_FILE_WRITE=TRUE\n",
    )
    for marker in required:
        if marker not in text:
            raise CanaryError("PAYLOAD_CONTRACT_MISSING:" + marker.strip())
    if len(text.splitlines()) != 7:
        raise CanaryError("PAYLOAD_LINE_COUNT")
    return value


def protected_snapshot() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in PROTECTED:
        digest, size = sha_file(path)
        result[str(path)] = {
            "sha256": digest,
            "bytes": size,
            "mode": path.stat().st_mode & 0o777,
        }
    return result


def target_snapshot() -> dict[str, Any]:
    if TARGET.exists():
        value = read_small(TARGET)
        return {
            "existed": True,
            "sha256": sha_bytes(value),
            "bytes": len(value),
            "mode": TARGET.stat().st_mode & 0o777,
        }
    return {"existed": False, "sha256": None, "bytes": 0, "mode": None}


def make_backup(before: dict[str, Any]) -> tuple[pathlib.Path, dict[str, Any]]:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = BACKUPS / (stamp + "_" + uuid.uuid4().hex[:10])
    backup_root.mkdir(parents=True, exist_ok=False)
    manifest = {
        "contract_id": CONTRACT_ID,
        "target": str(TARGET),
        "before": dict(before),
        "created_at_utc": utc_now(),
    }
    if before["existed"]:
        destination = backup_root / "target.preimage"
        shutil.copy2(TARGET, destination)
        value = read_small(destination)
        if sha_bytes(value) != before["sha256"]:
            raise CanaryError("BACKUP_SHA_MISMATCH")
        manifest["before"]["backup_file"] = str(destination)
    else:
        manifest["before"]["backup_file"] = None
    atomic_json(backup_root / "manifest.json", manifest)
    fsync_dir(backup_root)
    return backup_root, manifest


def validate_backup(manifest: dict[str, Any], backup_root: pathlib.Path) -> None:
    if manifest.get("contract_id") != CONTRACT_ID:
        raise CanaryError("BACKUP_CONTRACT")
    if manifest.get("target") != str(TARGET):
        raise CanaryError("BACKUP_TARGET")
    root = backup_root.resolve(strict=True)
    allowed = BACKUPS.resolve(strict=True)
    if root == allowed or not root.is_relative_to(allowed):
        raise CanaryError("BACKUP_PATH_ESCAPE")
    disk = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
    if disk != manifest:
        raise CanaryError("BACKUP_MANIFEST_READBACK")
    before = manifest["before"]
    if before["existed"]:
        backup_file = pathlib.Path(before["backup_file"])
        if not backup_file.resolve(strict=True).is_relative_to(root):
            raise CanaryError("BACKUP_FILE_ESCAPE")
        if sha_bytes(read_small(backup_file)) != before["sha256"]:
            raise CanaryError("BACKUP_FILE_SHA")


def restore_from_manifest(manifest: dict[str, Any], backup_root: pathlib.Path) -> dict[str, Any]:
    validate_backup(manifest, backup_root)
    before = manifest["before"]
    if before["existed"]:
        backup_file = pathlib.Path(before["backup_file"])
        atomic_write(TARGET, read_small(backup_file), int(before["mode"]))
        restored = target_snapshot()
        if not restored["existed"] or restored["sha256"] != before["sha256"]:
            raise CanaryError("ROLLBACK_RESTORE_MISMATCH")
    else:
        if TARGET.exists():
            if TARGET.is_symlink() or not TARGET.is_file():
                raise CanaryError("ROLLBACK_TARGET_NOT_REGULAR")
            TARGET.unlink()
            fsync_dir(TARGET.parent)
        restored = target_snapshot()
        if restored["existed"]:
            raise CanaryError("ROLLBACK_DELETE_FAILED")
    return restored


def run_install() -> dict[str, Any]:
    started = utc_now()
    assert_scope()
    payload = payload_bytes()
    expected_sha = sha_bytes(payload)
    backup_root: pathlib.Path | None = None
    manifest: dict[str, Any] | None = None
    before: dict[str, Any] | None = None
    protected_before: dict[str, dict[str, Any]] | None = None
    with production_lock():
        protected_before = protected_snapshot()
        before = target_snapshot()
        backup_root, manifest = make_backup(before)
        try:
            validate_backup(manifest, backup_root)
            atomic_write(TARGET, payload, int(before["mode"] or 0o644))
            after = target_snapshot()
            if not after["existed"] or after["sha256"] != expected_sha or after["bytes"] != len(payload):
                raise CanaryError("TARGET_READBACK_MISMATCH")
            protected_after = protected_snapshot()
            if protected_after != protected_before:
                raise CanaryError("PROTECTED_FILE_CHANGE")
            validate_backup(manifest, backup_root)
            last_success = {
                "contract_id": CONTRACT_ID,
                "target": str(TARGET),
                "public_path": "/video/task105-fast-canary.txt",
                "backup_root": str(backup_root),
                "manifest": manifest,
                "expected_sha256": expected_sha,
                "expected_bytes": len(payload),
                "protected_before": protected_before,
                "installed_at_utc": utc_now(),
            }
            atomic_json(LAST_SUCCESS, last_success)
        except Exception:
            restore_from_manifest(manifest, backup_root)
            raise
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "INSTALL",
        "production_write": True,
        "crm_write": False,
        "existing_site_file_write": False,
        "cloudflare_write": False,
        "dns_write": False,
        "target": str(TARGET),
        "changed_files": [str(TARGET)],
        "before": before,
        "after": after,
        "backup_root": str(backup_root),
        "backup_manifest": str(backup_root / "manifest.json"),
        "rollback_ready": True,
        "expected_sha256": expected_sha,
        "protected_before": protected_before,
        "protected_after": protected_after,
        "unexpected_changes": 0,
        "runtime_llm_tokens": 0,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def run_rollback() -> dict[str, Any]:
    started = utc_now()
    assert_scope()
    with production_lock():
        if LAST_SUCCESS.is_symlink() or not LAST_SUCCESS.is_file():
            raise CanaryError("LAST_SUCCESS_MISSING")
        last = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        if last.get("contract_id") != CONTRACT_ID:
            raise CanaryError("LAST_SUCCESS_CONTRACT")
        backup_root = pathlib.Path(last["backup_root"])
        manifest = last["manifest"]
        protected_now = protected_snapshot()
        if protected_now != last["protected_before"]:
            raise CanaryError("ROLLBACK_PROTECTED_DRIFT")
        restored = restore_from_manifest(manifest, backup_root)
        protected_after = protected_snapshot()
        if protected_after != protected_now:
            raise CanaryError("ROLLBACK_PROTECTED_CHANGE")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_write": False,
        "target": str(TARGET),
        "restored": restored,
        "rollback_source": str(backup_root),
        "protected_before": protected_now,
        "protected_after": protected_after,
        "unexpected_changes": 0,
        "runtime_llm_tokens": 0,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=tuple(RECEIPTS))
    args = parser.parse_args()
    try:
        value = {"install": run_install, "rollback": run_rollback}[args.mode]()
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
    REMOTE.mkdir(parents=True, exist_ok=True)
    atomic_json(RECEIPTS[args.mode], value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
