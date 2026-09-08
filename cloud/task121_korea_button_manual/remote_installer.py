#!/usr/bin/env python3
"""Atomic PythonAnywhere installer for the single TASK121 Korea button."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import stat
import tempfile
from types import ModuleType
from typing import Any


TASK_ID = "TASK121-KOREA-BUTTON"
CONTRACT = "UA-ART-CRM-KOREA-BUTTON-001-V1.0"
ROOT = pathlib.Path("/home/Carix")
REMOTE_DIR = ROOT / "autopilot_inbox/cloud/task_068_ferry_vin"
PATCHER_PATH = REMOTE_DIR / "task121_korea_patcher.py"
RECEIPT = REMOTE_DIR / "task121_korea_receipt.json"
STATE = REMOTE_DIR / "task121_korea_state.json"
BACKUP_ROOT = REMOTE_DIR / "task121_korea_backups"
START_SAFE = ROOT / "start_safe.py"
TARGETS = {
    "cars_ui.py": ROOT / "cars_ui.py",
    "konteyner.py": ROOT / "konteyner.py",
    "cars_schema.py": ROOT / "cars_schema.py",
}
EXPECTED_BEFORE = {
    "cars_ui.py": "2b1ef0bcfa700b7c87ccfb164b69b8ca173d460481936225e41344096c92062f",
    "konteyner.py": "72c03a1b8ab14279b2a2adbc681e112594d88c766d2aae7cc40e08b8aa004230",
    "cars_schema.py": "87f20a57248c3483ccb09955431cd840bb57bfdef6d2705e5fc048c201e14496",
}
MAX_BYTES = 4 * 1024 * 1024


class InstallError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def check_hash(value: str, code: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value or ""):
        raise InstallError(code)
    return value


def check_nonce(value: str) -> str:
    if not re.fullmatch(r"task121-[0-9]{6,20}-[0-9a-f]{12}", value or ""):
        raise InstallError("RUN_NONCE")
    return value


def read_regular(path: pathlib.Path) -> tuple[bytes, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1:
        raise InstallError("UNSAFE_FILE:" + str(path))
    if info.st_size < 1 or info.st_size > MAX_BYTES:
        raise InstallError("FILE_SIZE:" + str(path))
    value = path.read_bytes()
    if len(value) != info.st_size:
        raise InstallError("FILE_RACE:" + str(path))
    return value, stat.S_IMODE(info.st_mode)


def fsync_dir(path: pathlib.Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: pathlib.Path, value: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
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
        if temporary.exists():
            temporary.unlink()


def write_receipt(value: dict[str, Any]) -> None:
    atomic_write(RECEIPT, canonical(value), 0o600)


def snapshot() -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for name, path in list(TARGETS.items()) + [("start_safe.py", START_SAFE)]:
        value, mode = read_regular(path)
        files[name] = {"sha256": sha(value), "bytes": len(value), "mode": mode}
    return files


def target_bytes() -> dict[str, bytes]:
    return {name: read_regular(path)[0] for name, path in TARGETS.items()}


def assert_preimages(files: dict[str, dict[str, Any]]) -> None:
    for name, expected in EXPECTED_BEFORE.items():
        if files.get(name, {}).get("sha256") != expected:
            raise InstallError("LIVE_PREIMAGE_MISMATCH:" + name)


def load_patcher(expected_sha: str) -> ModuleType:
    check_hash(expected_sha, "PATCHER_SHA")
    value, _ = read_regular(PATCHER_PATH)
    if sha(value) != expected_sha:
        raise InstallError("PATCHER_IDENTITY")
    spec = importlib.util.spec_from_file_location("task121_korea_patcher", PATCHER_PATH)
    if spec is None or spec.loader is None:
        raise InstallError("PATCHER_IMPORT_SPEC")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_state(run_nonce: str, backup_sha: str | None = None) -> dict[str, Any]:
    raw, _ = read_regular(STATE)
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise InstallError("STATE_PARSE") from exc
    if value.get("task_id") != TASK_ID or value.get("run_nonce") != run_nonce:
        raise InstallError("STATE_IDENTITY")
    manifest_path = pathlib.Path(str(value.get("backup_manifest_path") or ""))
    if manifest_path.parent.parent != BACKUP_ROOT or manifest_path.name != "manifest.json":
        raise InstallError("BACKUP_PATH")
    manifest_raw, _ = read_regular(manifest_path)
    actual_sha = sha(manifest_raw)
    if actual_sha != value.get("backup_manifest_sha256"):
        raise InstallError("BACKUP_MANIFEST_STATE")
    if backup_sha is not None and actual_sha != backup_sha:
        raise InstallError("BACKUP_MANIFEST_IDENTITY")
    try:
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except Exception as exc:
        raise InstallError("BACKUP_MANIFEST_PARSE") from exc
    if (
        manifest.get("task_id") != TASK_ID
        or manifest.get("run_nonce") != run_nonce
        or manifest.get("backup_dir") != str(manifest_path.parent)
        or manifest.get("files") != value.get("before")
    ):
        raise InstallError("BACKUP_MANIFEST_CONTENT")
    return value


def backup(run_nonce: str) -> dict[str, Any]:
    before = snapshot()
    assert_preimages(before)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / (stamp + "-" + run_nonce[-12:])
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name, path in TARGETS.items():
        value, mode = read_regular(path)
        destination = backup_dir / name
        atomic_write(destination, value, mode)
        copied, copied_mode = read_regular(destination)
        if sha(copied) != before[name]["sha256"] or copied_mode != mode:
            raise InstallError("BACKUP_READBACK:" + name)
    manifest = {
        "schema_version": "UA-ART-TASK121-BACKUP-1",
        "task_id": TASK_ID,
        "run_nonce": run_nonce,
        "created_at": now(),
        "backup_dir": str(backup_dir),
        "files": before,
    }
    manifest_raw = canonical(manifest)
    manifest_sha = sha(manifest_raw)
    manifest_path = backup_dir / "manifest.json"
    atomic_write(manifest_path, manifest_raw, 0o600)
    state = {
        "schema_version": "UA-ART-TASK121-STATE-1",
        "task_id": TASK_ID,
        "run_nonce": run_nonce,
        "status": "BACKED_UP",
        "before": before,
        "backup_dir": str(backup_dir),
        "backup_manifest_path": str(manifest_path),
        "backup_manifest_sha256": manifest_sha,
        "updated_at": now(),
    }
    atomic_write(STATE, canonical(state), 0o600)
    return {
        "task_id": TASK_ID,
        "contract_id": CONTRACT,
        "run_nonce": run_nonce,
        "status": "PASS",
        "mode": "BACKUP",
        "backup_manifest_sha256": manifest_sha,
        "backup_dir": str(backup_dir),
        "before": before,
        "production_write": False,
        "unexpected_changes": 0,
    }


def expected_after(args: argparse.Namespace) -> dict[str, str]:
    values = {
        "cars_ui.py": args.expected_after_cars_ui,
        "konteyner.py": args.expected_after_konteyner,
        "cars_schema.py": args.expected_after_cars_schema,
    }
    for name, value in values.items():
        check_hash(value or "", "EXPECTED_AFTER:" + name)
        if value == EXPECTED_BEFORE[name]:
            raise InstallError("NO_CHANGE:" + name)
    return values


def _restore(state: dict[str, Any]) -> dict[str, str]:
    backup_dir = pathlib.Path(state["backup_dir"])
    restored: dict[str, str] = {}
    for name, path in TARGETS.items():
        meta = state["before"][name]
        value, _ = read_regular(backup_dir / name)
        if sha(value) != meta["sha256"]:
            raise InstallError("BACKUP_CORRUPT:" + name)
        atomic_write(path, value, int(meta["mode"]))
        check, check_mode = read_regular(path)
        if sha(check) != meta["sha256"] or check_mode != int(meta["mode"]):
            raise InstallError("RESTORE_READBACK:" + name)
        restored[name] = sha(check)
    return restored


def install(
    run_nonce: str,
    backup_sha: str,
    patcher_sha: str,
    after_hashes: dict[str, str],
) -> dict[str, Any]:
    state = load_state(run_nonce, backup_sha)
    if state.get("status") != "BACKED_UP":
        raise InstallError("STATE_NOT_BACKED_UP")
    current = snapshot()
    if current != state.get("before"):
        raise InstallError("LIVE_DRIFT_AFTER_BACKUP")
    patcher = load_patcher(patcher_sha)
    originals = target_bytes()
    candidates = {
        "cars_ui.py": patcher.patch_cars_ui(originals["cars_ui.py"].decode("utf-8")).encode("utf-8"),
        "konteyner.py": patcher.patch_konteyner(originals["konteyner.py"].decode("utf-8")).encode("utf-8"),
        "cars_schema.py": patcher.patch_schema(originals["cars_schema.py"].decode("utf-8")).encode("utf-8"),
    }
    generated = {name: sha(value) for name, value in candidates.items()}
    if generated != after_hashes:
        raise InstallError("CANDIDATE_HASH_MISMATCH")
    proof = patcher.verify(
        candidates["cars_ui.py"].decode("utf-8"),
        candidates["konteyner.py"].decode("utf-8"),
        candidates["cars_schema.py"].decode("utf-8"),
    )
    try:
        for name, path in TARGETS.items():
            atomic_write(path, candidates[name], int(current[name]["mode"]))
            check, check_mode = read_regular(path)
            if check != candidates[name] or check_mode != int(current[name]["mode"]):
                raise InstallError("INSTALL_READBACK:" + name)
        after = snapshot()
        for name, expected in after_hashes.items():
            if after[name]["sha256"] != expected:
                raise InstallError("INSTALLED_HASH_MISMATCH:" + name)
        if after["start_safe.py"] != state["before"]["start_safe.py"]:
            raise InstallError("PROTECTED_START_SAFE_CHANGED")
    except Exception:
        _restore(state)
        raise
    state.update(
        {
            "status": "INSTALLED",
            "after": after,
            "expected_after": after_hashes,
            "patcher_sha256": patcher_sha,
            "proof": proof,
            "updated_at": now(),
        }
    )
    atomic_write(STATE, canonical(state), 0o600)
    return {
        "task_id": TASK_ID,
        "contract_id": CONTRACT,
        "run_nonce": run_nonce,
        "status": "PASS",
        "mode": "INSTALL",
        "backup_manifest_sha256": backup_sha,
        "before": current,
        "after": after,
        "proof": proof,
        "production_write": "THREE_RUNTIME_FILES_ONLY",
        "unexpected_changes": 0,
    }


def verify(
    run_nonce: str,
    backup_sha: str,
    patcher_sha: str,
    after_hashes: dict[str, str],
) -> dict[str, Any]:
    state = load_state(run_nonce, backup_sha)
    if state.get("status") not in ("INSTALLED", "VERIFIED"):
        raise InstallError("STATE_NOT_INSTALLED")
    current = snapshot()
    for name, expected in after_hashes.items():
        if current[name]["sha256"] != expected:
            raise InstallError("POST_RESTART_HASH_MISMATCH:" + name)
    if current["start_safe.py"] != state["before"]["start_safe.py"]:
        raise InstallError("POST_RESTART_PROTECTED_DRIFT")
    patcher = load_patcher(patcher_sha)
    values = target_bytes()
    proof = patcher.verify(
        values["cars_ui.py"].decode("utf-8"),
        values["konteyner.py"].decode("utf-8"),
        values["cars_schema.py"].decode("utf-8"),
    )
    state.update({"status": "VERIFIED", "verified": current, "updated_at": now()})
    atomic_write(STATE, canonical(state), 0o600)
    return {
        "task_id": TASK_ID,
        "contract_id": CONTRACT,
        "run_nonce": run_nonce,
        "status": "PASS",
        "mode": "VERIFY",
        "backup_manifest_sha256": backup_sha,
        "files": current,
        "proof": proof,
        "production_write": False,
        "unexpected_changes": 0,
    }


def rollback(run_nonce: str, backup_sha: str) -> dict[str, Any]:
    state = load_state(run_nonce, backup_sha)
    restored = _restore(state)
    current = snapshot()
    if current != state.get("before"):
        raise InstallError("ROLLBACK_DRIFT")
    state.update({"status": "ROLLED_BACK", "restored": restored, "updated_at": now()})
    atomic_write(STATE, canonical(state), 0o600)
    return {
        "task_id": TASK_ID,
        "contract_id": CONTRACT,
        "run_nonce": run_nonce,
        "status": "PASS",
        "mode": "ROLLBACK",
        "backup_manifest_sha256": backup_sha,
        "restored_exact": True,
        "restored_sha256": restored,
        "production_write": "EXACT_ROLLBACK",
        "unexpected_changes": 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("backup", "install", "verify", "rollback"))
    parser.add_argument("--run-nonce", required=True)
    parser.add_argument("--backup-manifest-sha256", default="")
    parser.add_argument("--patcher-sha256", default="")
    parser.add_argument("--expected-after-cars-ui", default="")
    parser.add_argument("--expected-after-konteyner", default="")
    parser.add_argument("--expected-after-cars-schema", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_nonce = check_nonce(args.run_nonce)
    try:
        if args.mode == "backup":
            result = backup(run_nonce)
        elif args.mode == "rollback":
            result = rollback(
                run_nonce,
                check_hash(args.backup_manifest_sha256, "BACKUP_SHA"),
            )
        else:
            after_hashes = expected_after(args)
            backup_sha = check_hash(args.backup_manifest_sha256, "BACKUP_SHA")
            patcher_sha = check_hash(args.patcher_sha256, "PATCHER_SHA")
            if args.mode == "install":
                result = install(run_nonce, backup_sha, patcher_sha, after_hashes)
            else:
                result = verify(run_nonce, backup_sha, patcher_sha, after_hashes)
    except Exception as exc:
        result = {
            "task_id": TASK_ID,
            "contract_id": CONTRACT,
            "run_nonce": run_nonce,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "error": type(exc).__name__ + ":" + str(exc),
            "unexpected_changes": 0,
            "finished_at": now(),
        }
        write_receipt(result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    result["finished_at"] = now()
    write_receipt(result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
