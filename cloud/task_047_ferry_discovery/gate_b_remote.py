#!/usr/bin/env python3
"""Fail-closed Gate B installer for the approved TASK 063 candidates.

The script runs on PythonAnywhere.  It can replace only the fixed catalog and
generator allowlist below, reads candidates only from the isolated Gate A
directory, never opens CRM in write mode, and rolls replaced files back if any
post-write check fails.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import stat
import tempfile
from typing import Any

TASK = "task_063"
MODE = "FERRY_GATE_B_ATOMIC_PRODUCTION_INSTALL"
FIXED_SOURCE_ROOT = "/home/Carix"
FIXED_SAFE_ROOT = "/home/Carix/autopilot_inbox/cloud/task_047_ferry_discovery"
FIXED_CANDIDATE_ROOT = FIXED_SAFE_ROOT + "/gate_a_candidates"
FIXED_MANIFEST_PATH = FIXED_SAFE_ROOT + "/ferry_gate_b_manifest.json"
FIXED_BACKUP_PARENT = FIXED_SAFE_ROOT + "/gate_b_backups"
FIXED_LOCK_PATH = FIXED_SAFE_ROOT + "/ferry_gate_b.lock"
OWNER_APPROVAL = "TASK_063_GATE_B_APPROVED"
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_MANIFEST_BYTES = 200_000
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DEPLOYMENT_ID = re.compile(r"^task063-[a-z0-9-]{1,48}$")

VIDEO_PATHS = (
    "video/index.html",
    "video/katalog.html",
    "video/info.html",
    "video/podbor.html",
) + tuple("video/UA-%04d.html" % number for number in range(1, 11))
PYTHON_PATHS = ("stranica.py", "yadro.py")
ALLOWED_PATHS = VIDEO_PATHS + PYTHON_PATHS
MANIFEST_KEYS = {
    "task", "operation", "owner_approval", "deployment_id",
    "gate_a_generated_at_utc", "source_root", "candidate_root",
    "backup_root", "crm", "files",
}
FILE_KEYS = {
    "path", "kind", "source_sha256", "candidate_sha256", "candidate_size",
}
CRM_KEYS = {"path", "sha256", "id_count", "table", "id_column", "container_column"}


class GateBBlocked(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise GateBBlocked("duplicate_json_key:" + label)
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise GateBBlocked("invalid_json:" + label) from exc
    if not isinstance(value, dict):
        raise GateBBlocked("json_not_object:" + label)
    return value


def _real_root(path: str) -> str:
    real = os.path.realpath(path)
    if (
        not os.path.isabs(real)
        or real != os.path.normpath(path)
        or not os.path.isdir(real)
    ):
        raise GateBBlocked("invalid_root:" + path)
    return real


def _safe_join(root: str, rel_path: str) -> str:
    pure = pathlib.PurePosixPath(rel_path)
    if (
        not rel_path
        or pure.is_absolute()
        or ".." in pure.parts
        or "." in pure.parts
        or str(pure) != rel_path
    ):
        raise GateBBlocked("unsafe_relative_path:" + rel_path)
    root_real = os.path.realpath(root)
    target = os.path.normpath(os.path.join(root_real, *pure.parts))
    resolved_target = os.path.realpath(target)
    if (
        os.path.commonpath((root_real, target)) != root_real
        or os.path.commonpath((root_real, resolved_target)) != root_real
    ):
        raise GateBBlocked("path_escape:" + rel_path)
    return target


def _reject_symlink_parents(path: str) -> None:
    pure = pathlib.PurePath(os.path.abspath(path))
    current = pure.anchor
    for part in pure.parts[1:-1]:
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise GateBBlocked("parent_lstat_failed:" + current) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise GateBBlocked("unsafe_file_parent:" + current)


def _safe_read(path: str, *, max_bytes: int = MAX_FILE_BYTES) -> tuple[bytes, os.stat_result]:
    _reject_symlink_parents(path)
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise GateBBlocked("read_lstat_failed:" + path) from exc
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise GateBBlocked("not_regular_file:" + path)
    if before.st_nlink != 1:
        raise GateBBlocked("unexpected_hardlink:" + path)
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise GateBBlocked("file_size_invalid:" + path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise GateBBlocked("read_open_failed:" + path) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or opened.st_nlink != 1
        ):
            raise GateBBlocked("file_changed_during_open:" + path)
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise GateBBlocked("file_too_large:" + path)
        after = os.fstat(descriptor)
        if (
            after.st_size != total
            or after.st_mtime_ns != opened.st_mtime_ns
            or after.st_ctime_ns != opened.st_ctime_ns
        ):
            raise GateBBlocked("file_changed_during_read:" + path)
        return b"".join(chunks), after
    finally:
        os.close(descriptor)


def _fsync_directory(path: str) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_directory(path: str, *, allowed_parent: str) -> None:
    parent_real = os.path.realpath(allowed_parent)
    candidate = os.path.realpath(path)
    if os.path.commonpath((parent_real, candidate)) != parent_real:
        raise GateBBlocked("directory_escape:" + path)
    os.makedirs(path, mode=0o700, exist_ok=True)
    current = parent_real
    relative = os.path.relpath(candidate, parent_real)
    for part in pathlib.PurePath(relative).parts:
        current = os.path.join(current, part)
        info = os.lstat(current)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise GateBBlocked("unsafe_directory:" + current)


def _atomic_replace(path: str, data: bytes, mode: int) -> None:
    parent = os.path.dirname(path)
    if os.path.realpath(parent) != parent:
        raise GateBBlocked("unsafe_target_parent:" + parent)
    handle, temporary = tempfile.mkstemp(prefix=".task063-gate-b-", dir=parent)
    try:
        os.fchmod(handle, stat.S_IMODE(mode))
        offset = 0
        while offset < len(data):
            offset += os.write(handle, data[offset:])
        os.fsync(handle)
        os.close(handle)
        handle = -1
        os.replace(temporary, path)
        _fsync_directory(parent)
    finally:
        if handle >= 0:
            os.close(handle)
        try:
            if os.path.exists(temporary):
                os.unlink(temporary)
        except OSError:
            pass


def _write_backup(path: str, data: bytes, mode: int, backup_root: str) -> None:
    parent = os.path.dirname(path)
    _ensure_directory(parent, allowed_parent=backup_root)
    if os.path.exists(path):
        existing, _ = _safe_read(path)
        if existing != data:
            raise GateBBlocked("backup_conflict:" + path)
        return
    handle, temporary = tempfile.mkstemp(prefix=".task063-backup-", dir=parent)
    try:
        os.fchmod(handle, stat.S_IMODE(mode))
        offset = 0
        while offset < len(data):
            offset += os.write(handle, data[offset:])
        os.fsync(handle)
        os.close(handle)
        handle = -1
        os.replace(temporary, path)
        _fsync_directory(parent)
    finally:
        if handle >= 0:
            os.close(handle)
        try:
            if os.path.exists(temporary):
                os.unlink(temporary)
        except OSError:
            pass
    check, _ = _safe_read(path)
    if check != data:
        raise GateBBlocked("backup_readback_mismatch:" + path)


def _candidate_path(candidate_root: str, rel_path: str, kind: str) -> str:
    if kind == "html":
        return _safe_join(candidate_root, rel_path)
    if kind == "python":
        return _safe_join(candidate_root, "python/" + rel_path)
    raise GateBBlocked("invalid_file_kind:" + rel_path)


def _validate_manifest(
    manifest: dict[str, Any], *, enforce_fixed: bool
) -> tuple[str, str, str, list[dict[str, Any]]]:
    if set(manifest) != MANIFEST_KEYS:
        raise GateBBlocked("manifest_keys_invalid")
    if manifest.get("task") != TASK or manifest.get("operation") != "APPLY":
        raise GateBBlocked("manifest_operation_invalid")
    if manifest.get("owner_approval") != OWNER_APPROVAL:
        raise GateBBlocked("owner_approval_missing")
    deployment_id = manifest.get("deployment_id")
    if not isinstance(deployment_id, str) or not DEPLOYMENT_ID.fullmatch(deployment_id):
        raise GateBBlocked("deployment_id_invalid")
    generated = manifest.get("gate_a_generated_at_utc")
    if not isinstance(generated, str) or len(generated) > 64 or not generated.endswith("Z"):
        raise GateBBlocked("gate_a_timestamp_invalid")

    source_root = manifest.get("source_root")
    candidate_root = manifest.get("candidate_root")
    backup_root = manifest.get("backup_root")
    if not all(isinstance(value, str) for value in (source_root, candidate_root, backup_root)):
        raise GateBBlocked("manifest_root_type_invalid")
    if enforce_fixed:
        if source_root != FIXED_SOURCE_ROOT or candidate_root != FIXED_CANDIDATE_ROOT:
            raise GateBBlocked("manifest_fixed_root_invalid")
        expected_backup = FIXED_BACKUP_PARENT + "/" + deployment_id
        if backup_root != expected_backup:
            raise GateBBlocked("manifest_backup_root_invalid")
    source_root = _real_root(source_root)
    candidate_root = _real_root(candidate_root)
    backup_parent = os.path.dirname(backup_root)
    _ensure_directory(backup_parent, allowed_parent=backup_parent)
    _ensure_directory(backup_root, allowed_parent=backup_parent)

    crm = manifest.get("crm")
    if not isinstance(crm, dict) or set(crm) != CRM_KEYS:
        raise GateBBlocked("manifest_crm_invalid")
    if (
        crm.get("path") != "crm.db"
        or crm.get("table") != "cars"
        or crm.get("id_column") != "auto_number"
        or crm.get("container_column") != "sea_container"
        or crm.get("id_count") != 10
        or not isinstance(crm.get("sha256"), str)
        or not HEX64.fullmatch(crm["sha256"])
    ):
        raise GateBBlocked("manifest_crm_contract_invalid")

    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(ALLOWED_PATHS):
        raise GateBBlocked("manifest_files_invalid")
    by_path: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict) or set(item) != FILE_KEYS:
            raise GateBBlocked("manifest_file_entry_invalid")
        rel_path = item.get("path")
        if rel_path in by_path or rel_path not in ALLOWED_PATHS:
            raise GateBBlocked("manifest_file_path_invalid")
        expected_kind = "html" if rel_path in VIDEO_PATHS else "python"
        if item.get("kind") != expected_kind:
            raise GateBBlocked("manifest_file_kind_invalid:" + str(rel_path))
        for field in ("source_sha256", "candidate_sha256"):
            value = item.get(field)
            if not isinstance(value, str) or not HEX64.fullmatch(value):
                raise GateBBlocked("manifest_file_hash_invalid:" + str(rel_path))
        size = item.get("candidate_size")
        if not isinstance(size, int) or not 0 < size <= MAX_FILE_BYTES:
            raise GateBBlocked("manifest_file_size_invalid:" + str(rel_path))
        by_path[rel_path] = item
    if set(by_path) != set(ALLOWED_PATHS):
        raise GateBBlocked("manifest_file_set_invalid")
    return source_root, candidate_root, backup_root, [by_path[path] for path in ALLOWED_PATHS]


def run_gate_b(
    manifest_path: str,
    expected_manifest_sha256: str,
    *,
    enforce_fixed: bool = True,
    fail_after_replacements: int | None = None,
) -> dict[str, Any]:
    """Run an install; test-only arguments never come from the production CLI."""
    receipt: dict[str, Any] = {
        "mode": MODE,
        "task": TASK,
        "status": "BLOCKED",
        "generated_at_utc": _utc_now(),
        "manifest_sha256": expected_manifest_sha256,
        "gate_a_generated_at_utc": "",
        "source_root": "",
        "candidate_root": "",
        "backup_root": "",
        "owner_approval": OWNER_APPROVAL,
        "production_write": False,
        "production_files_changed": 0,
        "crm_write": False,
        "db_write": False,
        "service_reload": False,
        "gate_b_executed": True,
        "rollback_attempted": False,
        "rollback_completed": False,
        "crm_sha256_before": "",
        "crm_sha256_after": "",
        "files": [],
        "errors": [],
    }
    entries: list[dict[str, Any]] = []
    replaced: list[dict[str, Any]] = []
    try:
        if not isinstance(expected_manifest_sha256, str) or not HEX64.fullmatch(
            expected_manifest_sha256
        ):
            raise GateBBlocked("expected_manifest_hash_invalid")
        manifest_bytes, _ = _safe_read(manifest_path, max_bytes=MAX_MANIFEST_BYTES)
        if _sha256(manifest_bytes) != expected_manifest_sha256:
            raise GateBBlocked("manifest_hash_mismatch")
        manifest = _strict_json(manifest_bytes, "gate_b_manifest")
        source_root, candidate_root, backup_root, files = _validate_manifest(
            manifest, enforce_fixed=enforce_fixed
        )
        receipt.update(
            gate_a_generated_at_utc=manifest["gate_a_generated_at_utc"],
            source_root=source_root,
            candidate_root=candidate_root,
            backup_root=backup_root,
        )

        crm_path = _safe_join(source_root, manifest["crm"]["path"])
        crm_before, _ = _safe_read(crm_path)
        crm_sha = _sha256(crm_before)
        receipt["crm_sha256_before"] = crm_sha
        if crm_sha != manifest["crm"]["sha256"]:
            raise GateBBlocked("crm_hash_changed_before_install")

        for item in files:
            rel_path = item["path"]
            source_path = _safe_join(source_root, rel_path)
            candidate_path = _candidate_path(candidate_root, rel_path, item["kind"])
            source_bytes, source_stat = _safe_read(source_path)
            candidate_bytes, _ = _safe_read(candidate_path)
            source_sha = _sha256(source_bytes)
            candidate_sha = _sha256(candidate_bytes)
            if len(candidate_bytes) != item["candidate_size"]:
                raise GateBBlocked("candidate_size_mismatch:" + rel_path)
            if candidate_sha != item["candidate_sha256"]:
                raise GateBBlocked("candidate_hash_mismatch:" + rel_path)
            if source_sha not in {item["source_sha256"], item["candidate_sha256"]}:
                raise GateBBlocked("production_source_hash_mismatch:" + rel_path)
            if item["kind"] == "python":
                try:
                    compile(candidate_bytes.decode("utf-8"), rel_path, "exec")
                except (UnicodeDecodeError, SyntaxError) as exc:
                    raise GateBBlocked("candidate_compile_failed:" + rel_path) from exc
            backup_path = _safe_join(backup_root, rel_path)
            entries.append(
                {
                    "path": rel_path,
                    "source_path": source_path,
                    "backup_path": backup_path,
                    "before_bytes": source_bytes,
                    "candidate_bytes": candidate_bytes,
                    "mode": source_stat.st_mode,
                    "source_sha256": item["source_sha256"],
                    "candidate_sha256": item["candidate_sha256"],
                    "before_sha256": source_sha,
                    "backup_sha256": source_sha,
                    "after_sha256": source_sha,
                    "action": "PENDING",
                }
            )

        for entry in entries:
            _write_backup(
                entry["backup_path"], entry["before_bytes"], entry["mode"], backup_root
            )

        # Revalidate the whole bounded snapshot after backups and immediately
        # before the first write.  Backing up must not hide a concurrent edit.
        for entry in entries:
            current, _ = _safe_read(entry["source_path"])
            if _sha256(current) != entry["before_sha256"]:
                raise GateBBlocked("production_changed_after_preflight:" + entry["path"])
        crm_check, _ = _safe_read(crm_path)
        if _sha256(crm_check) != crm_sha:
            raise GateBBlocked("crm_changed_after_preflight")

        for entry in entries:
            if entry["before_sha256"] == entry["candidate_sha256"]:
                entry["action"] = "ALREADY_APPLIED"
                continue
            current, _ = _safe_read(entry["source_path"])
            if _sha256(current) != entry["before_sha256"]:
                raise GateBBlocked("production_changed_before_replace:" + entry["path"])
            _atomic_replace(
                entry["source_path"], entry["candidate_bytes"], entry["mode"]
            )
            replaced.append(entry)
            receipt["production_write"] = True
            receipt["production_files_changed"] = len(replaced)
            if fail_after_replacements is not None and len(replaced) >= fail_after_replacements:
                raise GateBBlocked("simulated_mid_install_failure")
            readback, _ = _safe_read(entry["source_path"])
            if _sha256(readback) != entry["candidate_sha256"]:
                raise GateBBlocked("production_readback_mismatch:" + entry["path"])
            entry["after_sha256"] = entry["candidate_sha256"]
            entry["action"] = "APPLIED"

        for entry in entries:
            readback, _ = _safe_read(entry["source_path"])
            if _sha256(readback) != entry["candidate_sha256"]:
                raise GateBBlocked("final_production_hash_mismatch:" + entry["path"])
            entry["after_sha256"] = entry["candidate_sha256"]
            if entry["action"] == "PENDING":
                entry["action"] = "ALREADY_APPLIED"

        crm_after, _ = _safe_read(crm_path)
        receipt["crm_sha256_after"] = _sha256(crm_after)
        if receipt["crm_sha256_after"] != crm_sha:
            raise GateBBlocked("crm_hash_changed_during_install")
        receipt["status"] = "PASS"
    except Exception as exc:
        label = str(exc) if isinstance(exc, GateBBlocked) else "unexpected_install_failure"
        receipt["errors"].append(label)
        if replaced:
            receipt["rollback_attempted"] = True
            rollback_errors = []
            for entry in reversed(replaced):
                try:
                    _atomic_replace(
                        entry["source_path"], entry["before_bytes"], entry["mode"]
                    )
                    restored, _ = _safe_read(entry["source_path"])
                    if _sha256(restored) != entry["before_sha256"]:
                        raise GateBBlocked("rollback_hash_mismatch:" + entry["path"])
                    entry["after_sha256"] = entry["before_sha256"]
                    entry["action"] = "ROLLED_BACK"
                except Exception:
                    rollback_errors.append("rollback_failed:" + entry["path"])
            for entry in entries:
                try:
                    restored, _ = _safe_read(entry["source_path"])
                    if _sha256(restored) != entry["before_sha256"]:
                        rollback_errors.append("rollback_state_mismatch:" + entry["path"])
                except Exception:
                    rollback_errors.append("rollback_state_unreadable:" + entry["path"])
            receipt["rollback_completed"] = not rollback_errors
            receipt["errors"].extend(rollback_errors)
            receipt["status"] = "ROLLED_BACK" if not rollback_errors else "BLOCKED"
        try:
            if receipt.get("source_root"):
                crm_path = _safe_join(receipt["source_root"], "crm.db")
                crm_after, _ = _safe_read(crm_path)
                receipt["crm_sha256_after"] = _sha256(crm_after)
        except Exception:
            receipt["errors"].append("crm_post_failure_check_failed")
    finally:
        receipt["files"] = [
            {
                "path": entry["path"],
                "source_sha256": entry["source_sha256"],
                "candidate_sha256": entry["candidate_sha256"],
                "before_sha256": entry["before_sha256"],
                "backup_sha256": entry["backup_sha256"],
                "after_sha256": entry["after_sha256"],
                "action": entry["action"],
            }
            for entry in entries
        ]
    return receipt


def main() -> int:
    expected_hash = os.environ.get("FERRY_GATE_B_MANIFEST_SHA256", "")
    expected_script_hash = os.environ.get("FERRY_GATE_B_SCRIPT_SHA256", "")
    approved = os.environ.get("FERRY_GATE_B_APPROVED", "")
    try:
        script_bytes, _ = _safe_read(os.path.abspath(__file__))
        script_hash_ok = (
            isinstance(expected_script_hash, str)
            and HEX64.fullmatch(expected_script_hash) is not None
            and _sha256(script_bytes) == expected_script_hash
        )
    except Exception:
        script_hash_ok = False
    if approved != OWNER_APPROVAL or not script_hash_ok:
        receipt = {
            "mode": MODE,
            "task": TASK,
            "status": "BLOCKED",
            "generated_at_utc": _utc_now(),
            "manifest_sha256": expected_hash,
            "gate_a_generated_at_utc": "",
            "source_root": "",
            "candidate_root": "",
            "backup_root": "",
            "owner_approval": approved,
            "production_write": False,
            "production_files_changed": 0,
            "crm_write": False,
            "db_write": False,
            "service_reload": False,
            "gate_b_executed": False,
            "rollback_attempted": False,
            "rollback_completed": False,
            "crm_sha256_before": "",
            "crm_sha256_after": "",
            "files": [],
            "errors": [
                "owner_approval_environment_missing"
                if approved != OWNER_APPROVAL
                else "remote_script_hash_mismatch"
            ],
        }
    else:
        lock_descriptor = os.open(FIXED_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                receipt = {
                    "mode": MODE,
                    "task": TASK,
                    "status": "BLOCKED",
                    "generated_at_utc": _utc_now(),
                    "manifest_sha256": expected_hash,
                    "gate_a_generated_at_utc": "",
                    "source_root": "",
                    "candidate_root": "",
                    "backup_root": "",
                    "owner_approval": approved,
                    "production_write": False,
                    "production_files_changed": 0,
                    "crm_write": False,
                    "db_write": False,
                    "service_reload": False,
                    "gate_b_executed": False,
                    "rollback_attempted": False,
                    "rollback_completed": False,
                    "crm_sha256_before": "",
                    "crm_sha256_after": "",
                    "files": [],
                    "errors": ["concurrent_gate_b_run"],
                }
            else:
                receipt = run_gate_b(FIXED_MANIFEST_PATH, expected_hash)
        finally:
            os.close(lock_descriptor)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
