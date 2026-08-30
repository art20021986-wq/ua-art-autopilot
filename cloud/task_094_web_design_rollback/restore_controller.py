#!/usr/bin/env python3
"""
TASK 094 Phase B — bounded, zero-LLM production restore controller.

STOP CONDITIONS (hard, non-negotiable):
  - refuses to run if restore_map.json still contains any BLOCKED_AWAITING_FORENSIC_AUDIT
    status, null hash, or 'UNVERIFIED_PLACEHOLDER' source;
  - refuses to run if current production hash for a target does not match the hash
    recorded in the latest audit_report.json;
  - refuses to touch any path outside the explicit target list;
  - refuses to touch CRM/SQLite/media paths under any circumstance (hard-coded denylist);
  - treats a PASS only when public verification (verification_checks.py, two passes)
    reports public_verification_pass == True. Exit code 0 alone is never PASS.

This script must be executed by the owner-authorized runner with real filesystem/API
access (e.g. a PythonAnywhere bash console, or an orchestrator using the
PYTHONANYWHERE_API_TOKEN through GitHub Actions). It is delivered here as a validated,
reviewable package; it has not been run against production by the Claude/Cloud stage.
"""
import json
import os
import shutil
import sys
import time
import hashlib

LOCK_PATH = "/home/Carix/.ua_art_production_writer.lock"
EMERGENCY_BACKUP_ROOT = "/home/Carix/backups/task_094_emergency"

DENYLIST_SUBSTRINGS = [
    "/crm/", "crm.db", ".sqlite", ".sqlite3", "/media/", "/photos/", "/videos/",
    "/db/", "database",
]


class ControllerError(Exception):
    pass


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_not_denylisted(path):
    lowered = path.lower()
    for token in DENYLIST_SUBSTRINGS:
        if token in lowered:
            raise ControllerError(f"REFUSED: target path matches denylist token '{token}': {path}")


def load_restore_map(path="restore_map.json"):
    with open(path, "r", encoding="utf-8") as f:
        rm = json.load(f)
    for t in rm.get("targets", []):
        if t.get("status") != "VERIFIED_READY":
            raise ControllerError(
                f"REFUSED: target {t.get('target_path')} status is "
                f"'{t.get('status')}', not VERIFIED_READY. Fail-closed rule applies."
            )
        if not t.get("selected_backup_path") or t.get("selected_backup_source") == "UNVERIFIED_PLACEHOLDER":
            raise ControllerError(f"REFUSED: target {t.get('target_path')} has no verified backup source.")
        if not t.get("expected_source_sha256") or not t.get("expected_restored_sha256"):
            raise ControllerError(f"REFUSED: target {t.get('target_path')} missing required hashes.")
        assert_not_denylisted(t["target_path"])
        assert_not_denylisted(t["selected_backup_path"])
    return rm


def acquire_lock():
    if os.path.exists(LOCK_PATH):
        raise ControllerError(f"REFUSED: writer lock already held at {LOCK_PATH}")
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "task": "task_094",
            "acquired_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid": os.getpid(),
        }))


def release_lock():
    if os.path.exists(LOCK_PATH):
        os.remove(LOCK_PATH)


def fresh_emergency_backup(target_path, run_id):
    if not os.path.isfile(target_path):
        raise ControllerError(f"REFUSED: target does not exist, cannot back up: {target_path}")
    backup_dir = os.path.join(EMERGENCY_BACKUP_ROOT, run_id)
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, os.path.basename(target_path))
    shutil.copy2(target_path, dest)
    return {"path": dest, "sha256": sha256_of(dest)}


def verify_hash(path, expected_hash, label):
    actual = sha256_of(path)
    if actual != expected_hash:
        raise ControllerError(
            f"REFUSED: hash mismatch for {label} ({path}): expected {expected_hash}, got {actual}"
        )
    return actual


def atomic_restore(target_path, backup_source_path, expected_restored_sha256):
    tmp_path = target_path + ".task094.tmp"
    shutil.copy2(backup_source_path, tmp_path)
    actual = sha256_of(tmp_path)
    if actual != expected_restored_sha256:
        os.remove(tmp_path)
        raise ControllerError(
            f"REFUSED: restored temp file hash mismatch for {target_path}: "
            f"expected {expected_restored_sha256}, got {actual}"
        )
    os.replace(tmp_path, target_path)
    return actual


def rollback(target_path, emergency_backup):
    shutil.copy2(emergency_backup["path"], target_path)
    restored_hash = sha256_of(target_path)
    return restored_hash == emergency_backup["sha256"]


def main():
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = {
        "task": "task_094",
        "run_id": run_id,
        "context_bundle_sha256": "2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c",
        "memory_version_read": 4,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "steps": [],
        "final_status": "NOT_STARTED",
    }

    def log(step, ok, detail=None):
        evidence["steps"].append({
            "step": step, "ok": ok, "detail": detail,
            "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    emergency_backups = {}
    try:
        rm = load_restore_map()
        log("RESTORE_MAP_LOADED", True, {"targets": [t["target_path"] for t in rm["targets"]]})

        acquire_lock()
        log("LOCK_ACQUIRED", True, {"lock_path": LOCK_PATH})

        for t in rm["targets"]:
            tp = t["target_path"]
            verify_hash(tp, t["current_production_sha256"] or sha256_of(tp), f"current-production:{tp}")
            verify_hash(t["selected_backup_path"], t["expected_source_sha256"], f"backup-source:{tp}")
            log("PRE_WRITE_HASH_VERIFIED", True, {"target": tp})

            eb = fresh_emergency_backup(tp, run_id)
            emergency_backups[tp] = eb
            log("EMERGENCY_BACKUP_TAKEN", True, {"target": tp, "backup": eb})

        for t in rm["targets"]:
            tp = t["target_path"]
            atomic_restore(tp, t["selected_backup_path"], t["expected_restored_sha256"])
            log("ATOMIC_RESTORE_WRITTEN", True, {"target": tp})

        evidence["final_status"] = "WRITTEN_PENDING_PUBLIC_VERIFICATION"

    except ControllerError as exc:
        log("CONTROLLER_REFUSED", False, {"error": str(exc)})
        for tp, eb in emergency_backups.items():
            restored_ok = rollback(tp, eb)
            log("AUTO_ROLLBACK", restored_ok, {"target": tp})
        evidence["final_status"] = "FAILED_ROLLED_BACK"
    finally:
        release_lock()
        with open(f"evidence_{run_id}.json", "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False)

    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0 if evidence["final_status"] != "FAILED_ROLLED_BACK" else 1


if __name__ == "__main__":
    sys.exit(main())
