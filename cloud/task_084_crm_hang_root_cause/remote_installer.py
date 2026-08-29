#!/usr/bin/env python3
"""Atomic PythonAnywhere installer for CRM-HANG-ROOT-CAUSE-084."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import py_compile
import shutil
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path("/home/Carix")
REMOTE = ROOT / "autopilot_inbox/cloud/task_083_catalog_dedup"
BACKUPS = ROOT / "backups/task_084"
MANIFEST = REMOTE / "task084_manifest.json"
LOCK = ROOT / ".ua_art_production_writer.lock"
CONTRACT = "CRM-HANG-ROOT-CAUSE-084-V1.0"
TARGETS = {
    "cars_ui.py": ROOT / "cars_ui.py",
    "team_bot.py": ROOT / "team_bot.py",
    "start_safe.py": ROOT / "start_safe.py",
    "crm_voice_watchdog.py": ROOT / "crm_voice_watchdog.py",
}
CANDIDATES = {name: REMOTE / ("task084_" + name + ".candidate") for name in TARGETS}
RECEIPTS = {
    "install": REMOTE / "task084_install_receipt.json",
    "postcheck": REMOTE / "task084_postcheck_receipt.json",
    "rollback": REMOTE / "task084_rollback_receipt.json",
}


class InstallError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha_bytes(path.read_bytes())


def atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".task084-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.close(descriptor)
        except Exception:
            pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_json(path: Path, value: dict) -> None:
    atomic_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def load_manifest() -> dict:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if value.get("contract_id") != CONTRACT:
        raise InstallError("MANIFEST_CONTRACT")
    if set(value.get("targets") or {}) != set(TARGETS):
        raise InstallError("MANIFEST_TARGET_SET")
    return value


def compile_file(path: Path) -> None:
    py_compile.compile(str(path), doraise=True)


def verify_candidate_files(manifest: dict) -> None:
    for name, path in CANDIDATES.items():
        if not path.exists():
            raise InstallError("CANDIDATE_MISSING:" + name)
        expected = manifest["targets"][name]["after_sha256"]
        if sha_file(path) != expected:
            raise InstallError("CANDIDATE_SHA:" + name)
        compile_file(path)


def verify_live_preimage(manifest: dict) -> None:
    for name, path in TARGETS.items():
        expected = manifest["targets"][name].get("before_sha256")
        if sha_file(path) != expected:
            raise InstallError("LIVE_PREIMAGE_DRIFT:" + name)


def verify_markers() -> dict:
    cars = TARGETS["cars_ui.py"].read_text(encoding="utf-8")
    team = TARGETS["team_bot.py"].read_text(encoding="utf-8")
    safe = TARGETS["start_safe.py"].read_text(encoding="utf-8")
    voice = TARGETS["crm_voice_watchdog.py"].read_text(encoding="utf-8")
    checks = {
        "cars_killable_voice": "crm_voice_watchdog as _v178_voice" in cars,
        "cars_old_fixed_deadline_removed": "hard_deadline = started + 4.65" not in cars,
        "cars_old_nonkillable_stt_removed": "asyncio.to_thread(ai.transcribe" not in cars,
        "team_killable_voice": "# UA-TASK084-KILLABLE-DRAFT-VOICE" in team,
        "team_old_nonkillable_stt_removed": "asyncio.to_thread(ai.transcribe, audio)" not in team,
        "menu_debounce": "# UA-TASK084-MENU-DEBOUNCE" in team,
        "startup_notice_debounce": "# UA-TASK084-STARTUP-NOTICE-DEBOUNCE" in team,
        "start_singleton": "# UA-TASK084-START-SINGLETON" in safe,
        "worker_process_group": "start_new_session=True" in voice,
        "worker_term_kill": "signal.SIGTERM" in voice and "signal.SIGKILL" in voice,
        "worker_limit_two": "MAX_CONCURRENT_WORKERS = 2" in voice,
    }
    if not all(checks.values()):
        raise InstallError("MARKER_CHECK:" + json.dumps(checks, sort_keys=True))
    return checks


def telegram_health() -> dict:
    result = {}
    for label, name in (("client", "bot_token.txt"), ("crm", "team_token.txt")):
        try:
            token = (ROOT / name).read_text(encoding="utf-8").strip()
            url = "https://api.telegram.org/bot%s/getMe" % urllib.parse.quote(token, safe=":")
            with urllib.request.urlopen(url, timeout=6) as response:
                value = json.loads(response.read(100_000).decode("utf-8"))
            result[label] = bool(value.get("ok"))
        except Exception as exc:
            result[label] = False
            result[label + "_error"] = type(exc).__name__
    return result


def singleton_lock_held() -> bool:
    """Prove that the restarted start_safe.py owns the singleton lock."""
    path = ROOT / ".start_safe.singleton.lock"
    with open(path, "a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def restore_from_backup(backup_dir: Path, manifest: dict) -> dict:
    restored = []
    removed = []
    for name, target in TARGETS.items():
        before = manifest["targets"][name].get("before_sha256")
        backup = backup_dir / name
        if before is None:
            if target.exists():
                target.unlink()
                removed.append(name)
            continue
        if not backup.exists() or sha_file(backup) != before:
            raise InstallError("BACKUP_INVALID:" + name)
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o600
        atomic_bytes(target, backup.read_bytes(), mode)
        restored.append(name)
    for name in restored:
        compile_file(TARGETS[name])
    return {"restored": restored, "removed": removed}


def run_install() -> dict:
    manifest = load_manifest()
    verify_candidate_files(manifest)
    changed = []
    backup_dir = None
    with open(LOCK, "a+", encoding="utf-8") as guard:
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        verify_live_preimage(manifest)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = BACKUPS / stamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        for name, target in TARGETS.items():
            if target.exists():
                shutil.copy2(target, backup_dir / name)
        atomic_json(backup_dir / "manifest.json", manifest)
        try:
            for name in ("crm_voice_watchdog.py", "cars_ui.py", "team_bot.py", "start_safe.py"):
                target = TARGETS[name]
                mode = target.stat().st_mode & 0o777 if target.exists() else 0o600
                atomic_bytes(target, CANDIDATES[name].read_bytes(), mode)
                changed.append(name)
            for path in TARGETS.values():
                compile_file(path)
            checks = verify_markers()
            for name, target in TARGETS.items():
                if sha_file(target) != manifest["targets"][name]["after_sha256"]:
                    raise InstallError("AFTER_SHA:" + name)
        except Exception:
            restore_from_backup(backup_dir, manifest)
            raise
        finally:
            fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    return {
        "contract_id": CONTRACT,
        "status": "PASS",
        "mode": "ATOMIC_INSTALL",
        "production_write": True,
        "crm_db_write": False,
        "media_write": False,
        "backup_dir": str(backup_dir),
        "changed_files": changed,
        "checks": checks,
        "before_sha256": {name: item.get("before_sha256") for name, item in manifest["targets"].items()},
        "after_sha256": {name: sha_file(path) for name, path in TARGETS.items()},
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def run_postcheck() -> dict:
    manifest = load_manifest()
    for name, target in TARGETS.items():
        compile_file(target)
        if sha_file(target) != manifest["targets"][name]["after_sha256"]:
            raise InstallError("POSTCHECK_SHA:" + name)
    checks = verify_markers()
    bots = telegram_health()
    if not bots.get("client") or not bots.get("crm"):
        raise InstallError("TELEGRAM_HEALTH:" + json.dumps(bots, sort_keys=True))
    singleton = singleton_lock_held()
    if not singleton:
        raise InstallError("START_SINGLETON_NOT_HELD")
    startup_state = ROOT / ".team_bot_start_notice"
    if not startup_state.exists():
        raise InstallError("STARTUP_NOTICE_GATE_NOT_ACTIVE")
    return {
        "contract_id": CONTRACT,
        "status": "PASS",
        "mode": "POST_RESTART_CHECK",
        "production_write": False,
        "crm_db_write": False,
        "checks": checks,
        "bots": bots,
        "start_singleton_held": singleton,
        "startup_notice_gate_active": True,
        "startup_notice_state_mtime": startup_state.stat().st_mtime,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def run_rollback() -> dict:
    manifest = load_manifest()
    install = json.loads(RECEIPTS["install"].read_text(encoding="utf-8"))
    backup = Path(str(install.get("backup_dir") or ""))
    if not str(backup).startswith(str(BACKUPS) + os.sep):
        raise InstallError("ROLLBACK_BACKUP_SCOPE")
    with open(LOCK, "a+", encoding="utf-8") as guard:
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        result = restore_from_backup(backup, manifest)
        fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    return {
        "contract_id": CONTRACT,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_db_write": False,
        "backup_dir": str(backup),
        **result,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=tuple(RECEIPTS))
    args = parser.parse_args()
    REMOTE.mkdir(parents=True, exist_ok=True)
    try:
        value = {"install": run_install, "postcheck": run_postcheck, "rollback": run_rollback}[args.mode]()
    except Exception as exc:
        value = {
            "contract_id": CONTRACT,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_db_write": False,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "finished_at_utc": utc_now(),
        }
    atomic_json(RECEIPTS[args.mode], value)
    print(json.dumps({"status": value["status"], "mode": value["mode"], "errors": value["errors"]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
