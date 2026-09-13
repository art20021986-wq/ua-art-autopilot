#!/usr/bin/env python3
"""Stage 2 source-only installation with immutable online backup and safe rollback.

Never imports the live CRM module, writes a live price, migrates a database,
restarts a process, or declares Telegram acceptance. Each operation is one-shot.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.machinery
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile

import patcher

TASK_ID = "TASK088-GE-PRICE-CRM-STAGE2-INSTALL"
PARENT_TASK_ID = "TASK088-GE-PRICE-CRM-STAGE2"
ROOT = Path("/home/Carix")
PROC = Path("/proc")
SAFE = ROOT / "autopilot_inbox/cloud/task_088_ge_price_crm_stage2"
BINDINGS = ("task_id", "run_id", "request_sha256", "transaction_id", "manifest_sha256", "nonce")
DEPENDENCY_KEYS = ("db_module_path", "parser_path", "utils_path")


class Refused(RuntimeError):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def value_sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition, code):
    if not condition:
        raise Refused(code)


def plain_file(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "NOT_PLAIN_FILE:" + str(path))
    return path


def atomic_bytes(path, data, mode=0o600):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".stage2-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n")


def bindings(plan):
    return {key: plan[key] for key in BINDINGS}


def readonly(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def database_facts(path):
    with contextlib.closing(readonly(path)) as conn:
        require(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "DATABASE_INTEGRITY_FAILED")
        schema = [list(row) for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cars)")}
        require({"id", "price_uah", "price_georgia", "price_history", "updated_at", "status"} <= columns,
                "STAGE1_SCHEMA_MISSING")
        audit_cols = {row[1] for row in conn.execute("PRAGMA table_info(audit)")}
        require({"actor_id", "action", "entity_type", "entity_id", "field", "old_value", "new_value", "created_at"} <= audit_cols,
                "AUDIT_SCHEMA_INCOMPATIBLE")
        rows = [dict(row) for row in conn.execute("SELECT * FROM cars ORDER BY id")]
        require(bool(rows), "NO_CARS")
        # Bytes are represented deterministically; full business rows never enter logs.
        row_hash = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False,
            default=lambda x: {"__bytes_hex__": bytes(x).hex()}, separators=(",", ":")).encode()).hexdigest()
        return {"integrity": "PASS", "schema_sha256": value_sha(schema), "cars_sha256": row_hash,
                "car_count": len(rows)}


def _process_snapshot(pid):
    proc = PROC / str(pid)
    stat_before = plain_file(proc / "stat").read_text()
    cmdline = plain_file(proc / "cmdline").read_bytes()
    stat_after = plain_file(proc / "stat").read_text()
    def ticks(stat):
        fields = stat[stat.rfind(")") + 2:].split()
        require(len(fields) >= 20, "PROCESS_STAT_INCOMPLETE")
        return fields[19]
    require(ticks(stat_before) == ticks(stat_after), "PROCESS_IDENTITY_CHANGED_DURING_READ")
    actual = {"pid": pid, "start_ticks": ticks(stat_after),
              "cmdline_sha256": hashlib.sha256(cmdline).hexdigest()}
    return actual, cmdline


def process_facts(expected):
    """Pin an explicit PID or discover exactly one process by its entire argv."""
    require(isinstance(expected, dict), "EXACT_PROCESS_REQUIRED")
    if expected.get("verification_mode") == "authenticated_supervisor":
        require(expected.get("command_argv") == ["python3.10", str(ROOT / "start_safe.py")]
                and expected.get("supervisor_id") == 266084, "EXACT_SUPERVISOR_SCOPE")
        evidence = expected.get("observed_evidence")
        require(isinstance(evidence, dict), "AUTHENTICATED_SUPERVISOR_EVIDENCE_REQUIRED")
        command = "python3.10 " + str(ROOT / "start_safe.py")
        require(evidence.get("source") == "PYTHONANYWHERE_AUTHENTICATED_API"
                and evidence.get("supervisor_id") == 266084 and evidence.get("command") == command
                and evidence.get("status") == "Running" and evidence.get("enabled") is True,
                "AUTHENTICATED_SUPERVISOR_IDENTITY_OR_STATE")
        try:
            observed_at = dt.datetime.fromisoformat(evidence["observed_at"].replace("Z", "+00:00"))
            require(observed_at.tzinfo is not None, "SUPERVISOR_OBSERVATION_TIMEZONE")
            age = (dt.datetime.now(dt.timezone.utc) - observed_at).total_seconds()
        except (KeyError, TypeError, ValueError):
            raise Refused("SUPERVISOR_OBSERVATION_TIMESTAMP")
        require(-30 <= age <= 300, "SUPERVISOR_OBSERVATION_STALE")
        # The controller observes the authenticated API before AND after each
        # operation. Worker namespaces cannot inspect the CRM's operating-system
        # PID, so this deliberately proves supervisor identity/state only.
        return {"verification_mode": "authenticated_supervisor", "supervisor_id": 266084,
                "command": command, "status": "Running", "enabled": True,
                "os_pid_inspection": "NO_OS_PID_INSPECTION"}
    if "pid" in expected:
        pid = expected.get("pid")
        require(isinstance(pid, int) and not isinstance(pid, bool) and pid > 1, "EXACT_PID_REQUIRED")
        actual, _ = _process_snapshot(pid)
        require(str(expected.get("start_ticks")) == actual["start_ticks"]
                and expected.get("cmdline_sha256") == actual["cmdline_sha256"], "PROCESS_IDENTITY_CHANGED")
        return actual
    command = expected.get("command_argv")
    require(command == ["python3.10", str(ROOT / "start_safe.py")], "EXACT_CRM_COMMAND_REQUIRED")
    require(isinstance(expected.get("supervisor_id"), int) and expected["supervisor_id"] > 0,
            "SUPERVISOR_REFERENCE_REQUIRED")
    matches = []
    for proc in PROC.iterdir():
        if not proc.name.isdigit() or int(proc.name) <= 1:
            continue
        try:
            cmdline = (proc / "cmdline").read_bytes()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        try:
            argv = [part.decode("utf-8") for part in cmdline.rstrip(b"\0").split(b"\0")]
        except UnicodeDecodeError:
            continue
        if (len(argv) == len(command) and Path(argv[0]).name == command[0]
                and argv[1:] == command[1:]):
            actual, verified_cmdline = _process_snapshot(int(proc.name))
            require(cmdline == verified_cmdline, "PROCESS_COMMAND_CHANGED_DURING_DISCOVERY")
            actual["supervisor_id"] = expected["supervisor_id"]
            matches.append(actual)
    require(len(matches) == 1, "EXACT_CRM_PROCESS_MATCH_COUNT:" + str(len(matches)))
    return matches[0]


def capacity(plan, db_path):
    quota = plan.get("quota", {})
    try:
        measured = dt.datetime.fromisoformat(quota["measured_at"].replace("Z", "+00:00"))
        age = (dt.datetime.now(dt.timezone.utc) - measured).total_seconds()
        free = int(quota["total_bytes"]) - int(quota["used_bytes"])
    except (KeyError, TypeError, ValueError):
        raise Refused("FRESH_ACCOUNT_QUOTA_REQUIRED")
    require(0 <= age <= 1800, "ACCOUNT_QUOTA_STALE")
    need = max(256 * 1024 * 1024, plain_file(db_path).stat().st_size * 4)
    require(free >= need, "ACCOUNT_QUOTA_INSUFFICIENT")
    require(shutil.disk_usage(SAFE).free >= need, "FILESYSTEM_CAPACITY_INSUFFICIENT")
    return {"measured_at": quota["measured_at"], "free_bytes": free, "required_bytes": need}


def validate_plan(plan, operation, directory):
    require(plan.get("task_id") == TASK_ID, "TASK_ID_MISMATCH")
    require(plan.get("operation") == operation, "OPERATION_MISMATCH")
    for key in BINDINGS:
        require(isinstance(plan.get(key), str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", plan[key])), "INVALID_BINDING:" + key)
    for key in ("request_sha256", "manifest_sha256"):
        require(bool(re.fullmatch(r"[0-9a-f]{64}", plan[key])), "INVALID_SHA256:" + key)
    require(directory == SAFE / "runs" / (plan["run_id"] + "-" + plan["request_sha256"]), "RUN_DIRECTORY_MISMATCH")
    require(not directory.is_symlink() and directory.resolve() == directory, "RUN_DIRECTORY_SYMLINK")
    require(plan.get("source_path") == str(ROOT / "cars_ui.py"), "SOURCE_PATH_MISMATCH")
    require(plan.get("db_path") == str(ROOT / "crm.db"), "DB_PATH_MISMATCH")
    require(plan.get("expected_source_sha256") == patcher.EXPECTED_SOURCE_SHA256, "SOURCE_BASELINE_NOT_REVIEWED")
    require(isinstance(plan.get("expected_candidate_sha256"), str)
            and bool(re.fullmatch(r"[0-9a-f]{64}", plan["expected_candidate_sha256"]))
            and plan["expected_candidate_sha256"] != "0" * 64, "APPROVED_CANDIDATE_HASH_REQUIRED")
    if plan.get("remote_source_sha256"):
        require(sha(__file__) == plan["remote_source_sha256"], "REMOTE_INSTALLER_HASH_MISMATCH")
    package_hashes = plan.get("remote_package_sha256")
    require(isinstance(package_hashes, dict), "REMOTE_PACKAGE_HASHES_REQUIRED")
    for filename in ("remote_installer.py", "patcher.py", "runtime.py"):
        require(sha(plain_file(Path(__file__).parent / filename)) == package_hashes.get(filename),
                "REMOTE_PACKAGE_HASH_MISMATCH:" + filename)


def protected_facts(plan):
    expected = plan.get("expected_dependency_sha256")
    require(isinstance(expected, dict), "DEPENDENCY_HASHES_REQUIRED")
    absent = plan.get("expected_absent_dependency_paths", [])
    require(isinstance(absent, list) and all(isinstance(path, str) for path in absent), "ABSENT_DEPENDENCY_LIST_INVALID")
    require(len(absent) == len(set(absent)) and set(absent) <= {str(ROOT / "price_parser.py")},
            "ONLY_OPTIONAL_PARSER_MAY_BE_ABSENT")
    require(not set(absent).intersection(expected), "DEPENDENCY_PRESENT_ABSENT_CONFLICT")
    for key in DEPENDENCY_KEYS:
        require(plan.get(key) in expected or (key == "parser_path" and plan.get(key) in absent),
                "DEPENDENCY_HASH_REQUIRED:" + key)
    required_paths = {"db_module_path": ROOT / "db.py", "parser_path": ROOT / "price_parser.py", "utils_path": ROOT / "cars_schema.py"}
    for key, path in required_paths.items():
        require(plan[key] == str(path), "DEPENDENCY_PATH_MISMATCH:" + key)
    actual = {}
    for path in absent:
        require(not os.path.lexists(path) and not os.path.lexists(str(ROOT / "price_parser")),
                "EXPECTED_ABSENT_PARSER_APPEARED")
        # A missing root file alone does not exclude a package or a parser in
        # site-packages. Resolve the top-level spec without loading any module.
        importlib.machinery.PathFinder.invalidate_caches()
        search_path = list(dict.fromkeys([str(ROOT)] + list(sys.path)))
        require(importlib.machinery.PathFinder.find_spec("price_parser", search_path) is None,
                "EXPECTED_ABSENT_PARSER_IMPORTABLE")
        actual[path] = "ABSENT"
    for path, fingerprint in expected.items():
        require(Path(path).is_absolute() and str(Path(path).resolve()).startswith(str(ROOT) + "/"), "DEPENDENCY_OUTSIDE_ROOT")
        actual[path] = sha(plain_file(path))
        require(actual[path] == fingerprint, "DEPENDENCY_HASH_CHANGED:" + path)
    receipt = plain_file(plan["stage1_receipt_path"])
    require(receipt == ROOT / "autopilot_inbox/cloud/task_088_ge_price_crm_stage1/receipt.json", "STAGE1_RECEIPT_PATH")
    require(sha(receipt) == plan.get("expected_stage1_receipt_sha256"), "STAGE1_RECEIPT_HASH_CHANGED")
    stage1 = json.loads(receipt.read_text())
    require(stage1.get("task_id") == "TASK088-GE-PRICE-CRM-STAGE1" and stage1.get("status") == "PASS", "STAGE1_NOT_PASSED")
    require(stage1.get("after_sha256", {}).get(str(ROOT / "cars_ui.py")) == patcher.EXPECTED_SOURCE_SHA256,
            "STAGE1_SOURCE_HASH_MISMATCH")
    return actual


def preflight(plan, require_original=True):
    protected = protected_facts(plan)
    source = plain_file(plan["source_path"])
    if require_original:
        require(sha(source) == plan["expected_source_sha256"], "LIVE_SOURCE_SHA_MISMATCH")
    process = process_facts(plan.get("exact_process"))
    quota = capacity(plan, plan["db_path"])
    facts = database_facts(plain_file(plan["db_path"]))
    if plan.get("expected_schema_sha256"):
        require(facts["schema_sha256"] == plan["expected_schema_sha256"], "LIVE_SCHEMA_CHANGED")
    return {"protected_source_sha256": protected, "database": facts, "exact_process": process, "quota": quota,
            "supervisor_observation": plan.get("exact_process", {}).get("observed_evidence")}


def backup(plan, directory):
    facts = preflight(plan)
    candidate, transformation = patcher.build_candidate(Path(plan["source_path"]).read_text())
    candidate_sha256 = patcher.digest(candidate)
    if plan.get("expected_candidate_sha256"):
        require(candidate_sha256 == plan["expected_candidate_sha256"], "APPROVED_CANDIDATE_HASH_MISMATCH")
    source_backup = directory / "cars_ui.original.py"
    require(not source_backup.exists(), "BACKUP_ALREADY_EXISTS")
    shutil.copy2(plan["source_path"], source_backup)
    require(sha(source_backup) == plan["expected_source_sha256"], "SOURCE_BACKUP_HASH_MISMATCH")
    candidate_path = directory / "cars_ui.candidate.py"
    atomic_bytes(candidate_path, candidate.encode(), Path(plan["source_path"]).stat().st_mode & 0o777)
    db_backup = directory / "crm.online-backup.db"
    require(not db_backup.exists(), "DATABASE_BACKUP_ALREADY_EXISTS")
    with contextlib.closing(readonly(plan["db_path"])) as live, sqlite3.connect(db_backup) as target:
        live.backup(target, pages=256, sleep=0.05)
    backup_facts = database_facts(db_backup)
    require(backup_facts == facts["database"], "DATABASE_CHANGED_DURING_BACKUP")
    require(database_facts(plan["db_path"]) == facts["database"], "LIVE_DATABASE_CHANGED_DURING_BACKUP_CHECK")
    require(protected_facts(plan) == facts["protected_source_sha256"], "PROTECTED_SOURCE_CHANGED")
    require(process_facts(plan.get("exact_process")) == facts["exact_process"], "PROCESS_IDENTITY_CHANGED_DURING_BACKUP")
    manifest = {**bindings(plan), "created_at": now(), "source_backup_sha256": sha(source_backup),
        "database_backup_sha256": sha(db_backup), "candidate_sha256": sha(candidate_path),
        "stage1_receipt_sha256": plan["expected_stage1_receipt_sha256"], "facts": facts,
        "transformation": transformation, "shadow_handler_acceptance": "NOT_PERFORMED",
        "runtime_compatibility": "PENDING_LIVE_CHECKS",
        "live_price_writes": False, "rollback": "ATOMIC_SOURCE_ONLY_DATABASE_BACKUP_AVAILABLE_MANUALLY"}
    path = directory / "backup-manifest.json"
    require(not path.exists(), "BACKUP_MANIFEST_ALREADY_EXISTS")
    write_json(path, manifest)
    return {"status": "BACKUP_PASS", "backup_manifest_sha256": sha(path), "backup_manifest_path": str(path),
            "shadow_handler_acceptance": "NOT_PERFORMED", "database": backup_facts,
            "candidate_sha256": candidate_sha256,
            "runtime_compatibility": "PENDING_LIVE_CHECKS", "process_verification": facts["exact_process"],
            "supervisor_observation": facts.get("supervisor_observation")}


def load_backup(plan, directory):
    path = plain_file(directory / "backup-manifest.json")
    require(sha(path) == plan.get("backup_manifest_sha256"), "BACKUP_MANIFEST_HASH_MISMATCH")
    manifest = json.loads(path.read_text())
    require(manifest["candidate_sha256"] == plan.get("expected_candidate_sha256"), "APPROVED_CANDIDATE_HASH_MISMATCH")
    require(bindings(manifest) == bindings(plan), "BACKUP_IDENTITY_MISMATCH")
    for filename, key in (("cars_ui.original.py", "source_backup_sha256"), ("crm.online-backup.db", "database_backup_sha256"),
                          ("cars_ui.candidate.py", "candidate_sha256")):
        require(sha(plain_file(directory / filename)) == manifest[key], "BACKUP_ARTIFACT_HASH_MISMATCH:" + filename)
    return manifest


def execute(plan, directory):
    manifest = load_backup(plan, directory)
    facts = preflight(plan)
    require(facts["database"] == manifest["facts"]["database"], "DATABASE_CHANGED_AFTER_BACKUP")
    require(facts["exact_process"] == manifest["facts"]["exact_process"], "PROCESS_IDENTITY_CHANGED_AFTER_BACKUP")
    candidate, _ = patcher.build_candidate(Path(plan["source_path"]).read_text())
    require(patcher.digest(candidate) == manifest["candidate_sha256"], "CANDIDATE_DRIFT")
    source = Path(plan["source_path"])
    require(sha(source) == manifest["source_backup_sha256"], "SOURCE_CHANGED_BEFORE_REPLACE")
    atomic_bytes(source, candidate.encode(), source.stat().st_mode & 0o777)
    require(sha(source) == manifest["candidate_sha256"], "INSTALLED_HASH_MISMATCH")
    require(protected_facts(plan) == manifest["facts"]["protected_source_sha256"], "PROTECTED_SOURCE_CHANGED")
    return {"status": "INSTALLED_AWAITING_VERIFICATION", "installed_sha256": sha(source),
            "process_verification": facts["exact_process"], "supervisor_observation": facts.get("supervisor_observation"),
            "other_ast_nodes_preserved": True, "backup_manifest_sha256": plan["backup_manifest_sha256"]}


def verify(plan, directory):
    manifest = load_backup(plan, directory)
    process = process_facts(plan.get("exact_process"))
    require(process == manifest["facts"]["exact_process"], "PROCESS_IDENTITY_CHANGED_AFTER_BACKUP")
    require(sha(plain_file(plan["source_path"])) == manifest["candidate_sha256"], "INSTALLED_HASH_MISMATCH")
    require(protected_facts(plan) == manifest["facts"]["protected_source_sha256"], "PROTECTED_SOURCE_CHANGED")
    facts = database_facts(plan["db_path"])
    require(facts == manifest["facts"]["database"], "LIVE_DATABASE_CHANGED")
    return {"status": "INSTALLATION_VERIFIED", "scope": "INSTALLATION_AND_SOURCE_DB_READONLY_VERIFY",
            "process_verification": process, "supervisor_observation": plan.get("exact_process", {}).get("observed_evidence"),
            "installed_sha256": manifest["candidate_sha256"], "database": facts,
            "stage2_acceptance": "PENDING_TELEGRAM_CHECKS", "bot_restart": "NOT_PERFORMED",
            "code_activation": "PENDING_RESTART", "protected_sources_unchanged": True,
            "database_unchanged": True, "source_installed": True, "rollback_ready": True,
            "backup_manifest_sha256": plan["backup_manifest_sha256"]}


def rollback(plan, directory):
    manifest = load_backup(plan, directory)
    source = plain_file(plan["source_path"])
    current = sha(source)
    require(current in (manifest["source_backup_sha256"], manifest["candidate_sha256"]), "ROLLBACK_SOURCE_DRIFT")
    require(protected_facts(plan) == manifest["facts"]["protected_source_sha256"], "PROTECTED_SOURCE_CHANGED")
    before_database = database_facts(plan["db_path"])
    if current != manifest["source_backup_sha256"]:
        atomic_bytes(source, (directory / "cars_ui.original.py").read_bytes(), source.stat().st_mode & 0o777)
    require(sha(source) == manifest["source_backup_sha256"], "ROLLBACK_HASH_MISMATCH")
    require(database_facts(plan["db_path"]) == before_database, "DATABASE_CHANGED_DURING_ROLLBACK")
    require(protected_facts(plan) == manifest["facts"]["protected_source_sha256"], "PROTECTED_SOURCE_CHANGED")
    return {"status": "ROLLED_BACK", "source_sha256": sha(source),
            "protected_sources_unchanged": True, "database_unchanged": True, "restored": True,
            "backup_manifest_sha256": plan["backup_manifest_sha256"], "database_restore": "NOT_NEEDED_NO_LIVE_DB_WRITES",
            "bot_restart": "NOT_PERFORMED"}


def run_operation(plan, operation, directory):
    directory = Path(directory)
    validate_plan(plan, operation, directory)
    with open(SAFE / "installation.lock", "a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused("OTHER_STAGE2_OPERATION_RUNNING")
        claims = SAFE / "claims"
        claims.mkdir(exist_ok=True)
        for label, identity in (("nonce", plan["nonce"]), ("request", plan["request_sha256"])):
            identity_path = claims / (label + "-" + identity + ".json")
            try:
                identity_fd = os.open(identity_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                require(json.loads(plain_file(identity_path).read_text()) == bindings(plan), "IDENTITY_ALREADY_CLAIMED:" + label)
            else:
                with os.fdopen(identity_fd, "wb") as stream:
                    stream.write(canonical(bindings(plan)))
                    stream.flush()
                    os.fsync(stream.fileno())
        claim = directory / (operation + "-started.json")
        fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical({**bindings(plan), "operation": operation, "started_at": now()}))
            stream.flush()
            os.fsync(stream.fileno())
        result = {**bindings(plan), "operation": operation, "started_at": now(), "status": "FAIL",
                  "live_price_writes": False, "site_write": False, "migration": False,
                  "telegram_ui_acceptance": "NOT_PERFORMED", "parent_stage2_receipt_created": False}
        try:
            result.update(globals()[operation](plan, directory))
        except Exception as exc:
            result["error"] = type(exc).__name__ + ":" + str(exc)
        result["finished_at"] = now()
        write_json(directory / (operation + "-result.json"), result)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True, choices=("backup", "execute", "verify", "rollback"))
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    path = plain_file(args.plan).resolve()
    try:
        result = run_operation(json.loads(path.read_text()), args.operation, path.parent)
    except Exception as exc:
        result = {"task_id": TASK_ID, "status": "FAIL", "operation": args.operation,
                  "error": type(exc).__name__ + ":" + str(exc), "live_price_writes": False}
        # Refuse to overwrite previous receipts on a replay or identity mismatch.
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
