#!/usr/bin/env python3
"""Atomic remote executor for TASK105 STANDARD production canary.

The suite exercises three bounded STANDARD cases against dedicated static
canary files. Existing site pages, CRM data, media, application code,
Cloudflare and DNS are never written. A single restorable pre-suite backup is
created and automatically restored on any failed invariant.
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

CONTRACT_ID = "UA-ART-STANDARD-PRODUCTION-CANARY-105-V1.0"
ROOT = pathlib.Path("/home/Carix")
REMOTE = ROOT / "autopilot_inbox/cloud/task_105_fast_pipeline_phase4"
PAYLOADS = {
    "a_v1": REMOTE / "task105_standard_a_v1.txt",
    "a_v2": REMOTE / "task105_standard_a_v2.txt",
    "b_v1": REMOTE / "task105_standard_b_v1.txt",
    "b_temp": REMOTE / "task105_standard_b_temp.txt",
    "c_v1": REMOTE / "task105_standard_c_v1.txt",
}
TARGETS = {
    "a": ROOT / "video/task105-standard-canary-a.txt",
    "b": ROOT / "video/task105-standard-canary-b.txt",
    "c": ROOT / "video/task105-standard-canary-c.txt",
}
LOCK = ROOT / ".ua_art_production_writer.lock"
BACKUPS = ROOT / "backups/task_105_standard_canary"
LAST_SUCCESS = REMOTE / "task105_standard_canary_last_success.json"
RECEIPTS = {
    "install": REMOTE / "task105_standard_canary_install_receipt.json",
    "postcheck": REMOTE / "task105_standard_canary_postcheck_receipt.json",
    "rollback": REMOTE / "task105_standard_canary_rollback_receipt.json",
}
PROTECTED = (
    ROOT / "crm.db",
    ROOT / "video/index.html",
    ROOT / "video/katalog.html",
)
MAX_CANARY_BYTES = 32 * 1024
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
    digest = hashlib.sha256()
    total = 0
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
    if len(value) > MAX_CANARY_BYTES:
        raise CanaryError("CANARY_TOO_LARGE:" + str(path))
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
        raise CanaryError("TARGET_PARENT_SYMLINK:" + str(path.parent))
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".task105-standard.tmp",
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
    encoded = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
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
    expected = {
        "a": ROOT / "video/task105-standard-canary-a.txt",
        "b": ROOT / "video/task105-standard-canary-b.txt",
        "c": ROOT / "video/task105-standard-canary-c.txt",
    }
    if TARGETS != expected:
        raise CanaryError("TARGET_SCOPE_CHANGED")
    video = (ROOT / "video").resolve(strict=True)
    for name, path in TARGETS.items():
        if path.parent.resolve(strict=True) != video:
            raise CanaryError("TARGET_PARENT_SCOPE:" + name)
        if path.is_symlink():
            raise CanaryError("TARGET_SYMLINK:" + name)
    if BACKUPS.resolve(strict=False) != (
        ROOT / "backups/task_105_standard_canary"
    ).resolve(strict=False):
        raise CanaryError("BACKUP_SCOPE_CHANGED")


def payload_bytes() -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for key, path in PAYLOADS.items():
        value = read_small(path)
        if not value.endswith(b"\n"):
            raise CanaryError("PAYLOAD_FINAL_NEWLINE:" + key)
        text = value.decode("utf-8")
        required = (
            "UA_ART_STANDARD_PIPELINE_CANARY\n",
            "CONTRACT_ID=" + CONTRACT_ID + "\n",
            "PAYLOAD_KEY=" + key + "\n",
            "NO_CRM_WRITE=TRUE\n",
            "NO_EXISTING_SITE_FILE_WRITE=TRUE\n",
        )
        for marker in required:
            if marker not in text:
                raise CanaryError("PAYLOAD_CONTRACT_MISSING:" + key + ":" + marker.strip())
        values[key] = value
    if len({sha_bytes(value) for value in values.values()}) != len(values):
        raise CanaryError("PAYLOAD_SHA_NOT_UNIQUE")
    return values


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


def target_snapshot(path: pathlib.Path) -> dict[str, Any]:
    if path.exists():
        value = read_small(path)
        return {
            "existed": True,
            "sha256": sha_bytes(value),
            "bytes": len(value),
            "mode": path.stat().st_mode & 0o777,
        }
    return {"existed": False, "sha256": None, "bytes": 0, "mode": None}


def targets_snapshot() -> dict[str, dict[str, Any]]:
    return {name: target_snapshot(path) for name, path in TARGETS.items()}


def make_backup(before: dict[str, dict[str, Any]]) -> tuple[pathlib.Path, dict[str, Any]]:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = BACKUPS / (stamp + "_" + uuid.uuid4().hex[:10])
    backup_root.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "targets": {name: str(path) for name, path in TARGETS.items()},
        "before": json.loads(json.dumps(before)),
        "created_at_utc": utc_now(),
    }
    for name, metadata in manifest["before"].items():
        if metadata["existed"]:
            destination = backup_root / (name + ".preimage")
            shutil.copy2(TARGETS[name], destination)
            if sha_bytes(read_small(destination)) != metadata["sha256"]:
                raise CanaryError("BACKUP_SHA_MISMATCH:" + name)
            metadata["backup_file"] = str(destination)
        else:
            metadata["backup_file"] = None
    atomic_json(backup_root / "manifest.json", manifest)
    fsync_dir(backup_root)
    return backup_root, manifest


def validate_backup(manifest: dict[str, Any], backup_root: pathlib.Path) -> None:
    if manifest.get("contract_id") != CONTRACT_ID:
        raise CanaryError("BACKUP_CONTRACT")
    if manifest.get("targets") != {name: str(path) for name, path in TARGETS.items()}:
        raise CanaryError("BACKUP_TARGETS")
    root = backup_root.resolve(strict=True)
    allowed = BACKUPS.resolve(strict=True)
    if root == allowed or not root.is_relative_to(allowed):
        raise CanaryError("BACKUP_PATH_ESCAPE")
    disk = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
    if disk != manifest:
        raise CanaryError("BACKUP_MANIFEST_READBACK")
    for name, metadata in manifest["before"].items():
        if metadata["existed"]:
            backup_file = pathlib.Path(metadata["backup_file"])
            if not backup_file.resolve(strict=True).is_relative_to(root):
                raise CanaryError("BACKUP_FILE_ESCAPE:" + name)
            if sha_bytes(read_small(backup_file)) != metadata["sha256"]:
                raise CanaryError("BACKUP_FILE_SHA:" + name)


def restore_initial(manifest: dict[str, Any], backup_root: pathlib.Path) -> dict[str, Any]:
    validate_backup(manifest, backup_root)
    restored: dict[str, Any] = {}
    for name, metadata in manifest["before"].items():
        target = TARGETS[name]
        if metadata["existed"]:
            backup_file = pathlib.Path(metadata["backup_file"])
            atomic_write(target, read_small(backup_file), int(metadata["mode"]))
        else:
            if target.exists():
                if target.is_symlink() or not target.is_file():
                    raise CanaryError("ROLLBACK_TARGET_NOT_REGULAR:" + name)
                target.unlink()
                fsync_dir(target.parent)
        snapshot = target_snapshot(target)
        if snapshot["existed"] != metadata["existed"]:
            raise CanaryError("ROLLBACK_EXISTENCE:" + name)
        if metadata["existed"] and snapshot["sha256"] != metadata["sha256"]:
            raise CanaryError("ROLLBACK_SHA:" + name)
        restored[name] = snapshot
    return restored


def assert_target(path: pathlib.Path, expected: bytes, label: str) -> dict[str, Any]:
    actual = read_small(path)
    if actual != expected:
        raise CanaryError("TARGET_MISMATCH:" + label)
    return {
        "path": str(path),
        "sha256": sha_bytes(actual),
        "bytes": len(actual),
        "mode": path.stat().st_mode & 0o777,
    }


def run_install() -> dict[str, Any]:
    started = utc_now()
    assert_scope()
    payloads = payload_bytes()
    with production_lock():
        protected_before = protected_snapshot()
        before = targets_snapshot()
        backup_root, manifest = make_backup(before)
        cases: list[dict[str, Any]] = []
        try:
            atomic_write(TARGETS["a"], payloads["a_v1"], 0o644)
            atomic_write(TARGETS["b"], payloads["b_v1"], 0o644)
            cases.append({
                "case_id": "STANDARD-CASE-1-MULTIFILE",
                "status": "PASS",
                "targets": [
                    assert_target(TARGETS["a"], payloads["a_v1"], "a_v1"),
                    assert_target(TARGETS["b"], payloads["b_v1"], "b_v1"),
                ],
            })

            atomic_write(TARGETS["a"], payloads["a_v2"], 0o644)
            atomic_write(TARGETS["c"], payloads["c_v1"], 0o644)
            cases.append({
                "case_id": "STANDARD-CASE-2-UPDATE-AND-CREATE",
                "status": "PASS",
                "targets": [
                    assert_target(TARGETS["a"], payloads["a_v2"], "a_v2"),
                    assert_target(TARGETS["c"], payloads["c_v1"], "c_v1"),
                ],
            })

            b_v1 = read_small(TARGETS["b"])
            atomic_write(TARGETS["b"], payloads["b_temp"], 0o644)
            assert_target(TARGETS["b"], payloads["b_temp"], "b_temp")
            atomic_write(TARGETS["b"], b_v1, 0o644)
            cases.append({
                "case_id": "STANDARD-CASE-3-ROLLBACK-DRILL",
                "status": "PASS",
                "target": assert_target(TARGETS["b"], payloads["b_v1"], "b_restored"),
            })

            protected_after = protected_snapshot()
            if protected_before != protected_after:
                raise CanaryError("PROTECTED_DRIFT")
            final_expected = {
                "a": sha_bytes(payloads["a_v2"]),
                "b": sha_bytes(payloads["b_v1"]),
                "c": sha_bytes(payloads["c_v1"]),
            }
            final_targets = {
                name: assert_target(TARGETS[name], payloads[key], name)
                for name, key in (("a", "a_v2"), ("b", "b_v1"), ("c", "c_v1"))
            }
            manifest.update({
                "backup_root": str(backup_root),
                "protected_before": protected_before,
                "final_expected": final_expected,
                "cases": cases,
                "installed_at_utc": utc_now(),
            })
            atomic_json(LAST_SUCCESS, manifest)
        except Exception:
            restore_initial(manifest, backup_root)
            if protected_snapshot() != protected_before:
                raise CanaryError("LOCAL_ROLLBACK_PROTECTED_DRIFT")
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
        "case_count": 3,
        "cases": cases,
        "before": before,
        "after": targets_snapshot(),
        "final_targets": final_targets,
        "backup_root": str(backup_root),
        "backup_manifest": str(backup_root / "manifest.json"),
        "rollback_ready": True,
        "protected_before": protected_before,
        "protected_after": protected_after,
        "changed_files": [str(TARGETS[name]) for name in ("a", "b", "c")],
        "unexpected_changes": 0,
        "runtime_llm_tokens": 0,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def load_last_success() -> tuple[pathlib.Path, dict[str, Any]]:
    if not LAST_SUCCESS.is_file() or LAST_SUCCESS.is_symlink():
        raise CanaryError("LAST_SUCCESS_MISSING")
    manifest = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
    backup_root = pathlib.Path(manifest["backup_root"])
    validate_backup(manifest, backup_root)
    return backup_root, manifest


def run_postcheck() -> dict[str, Any]:
    started = utc_now()
    assert_scope()
    with production_lock():
        _, manifest = load_last_success()
        current_protected = protected_snapshot()
        if current_protected != manifest["protected_before"]:
            raise CanaryError("POSTCHECK_PROTECTED_DRIFT")
        current = targets_snapshot()
        for name, expected in manifest["final_expected"].items():
            if not current[name]["existed"] or current[name]["sha256"] != expected:
                raise CanaryError("POSTCHECK_TARGET_DRIFT:" + name)
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "POSTCHECK",
        "production_write": False,
        "crm_write": False,
        "targets": current,
        "protected": current_protected,
        "case_count": len(manifest["cases"]),
        "runtime_llm_tokens": 0,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def run_rollback() -> dict[str, Any]:
    started = utc_now()
    assert_scope()
    with production_lock():
        backup_root, manifest = load_last_success()
        protected_before = protected_snapshot()
        restored = restore_initial(manifest, backup_root)
        protected_after = protected_snapshot()
        if protected_before != protected_after:
            raise CanaryError("ROLLBACK_PROTECTED_DRIFT")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_write": False,
        "restored": restored,
        "protected_before": protected_before,
        "protected_after": protected_after,
        "rollback_source": str(backup_root),
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
        result = {
            "install": run_install,
            "postcheck": run_postcheck,
            "rollback": run_rollback,
        }[args.mode]()
    except Exception as exc:
        result = {
            "contract_id": CONTRACT_ID,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_write": False,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "finished_at_utc": utc_now(),
        }
    atomic_json(RECEIPTS[args.mode], result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
