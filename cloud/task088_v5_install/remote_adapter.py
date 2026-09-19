"""Scoped remote Stage 3 operations, called only by the canonical controller.

No bot restart or task activation. PREPARING creates a real full backup; OPEN
installs/verifies; ROLLING_BACK restores exact own candidates and empty new
schema only. Newer files or any v5 operation/history prevent destructive restore.
"""
from datetime import datetime, timezone
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile

import install_package as E

BINDINGS = ("task_id", "request_sha256", "run_id", "transaction_id", "manifest_sha256")


def _phase(operation):
    return "PREPARING" if operation == "backup" else "ROLLING_BACK" if operation == "rollback" else "OPEN"


def load_operation(operation_plan, *, test_root=None, expected_payload_sha256=None):
    raw = E._read(Path(operation_plan))
    if expected_payload_sha256 is not None and E.sha(raw) != expected_payload_sha256:
        raise E.InstallError("REMOTE_OPERATION_PLAN_DRIFT")
    payload = json.loads(raw)
    operation = payload.get("operation")
    if operation not in ("backup", "execute", "verify", "rollback"):
        raise E.InstallError("EXACT_REMOTE_OPERATION_REQUIRED")
    root = Path(test_root) if test_root else E.LIVE_ROOT
    if test_root and root == E.LIVE_ROOT:
        raise E.InstallError("TEST_ROOT_CANNOT_BE_PRODUCTION")
    plan = payload["install_plan"]
    evidence = {name: content.encode("utf-8") for name, content in payload["canonical_evidence"].items()}
    stage = Path(payload["preflight_directory"])
    expected_parent = root / "autopilot_inbox/cloud"
    if (not stage.is_relative_to(expected_parent) or any(p.is_symlink() for p in (stage, *stage.parents))
            or not stage.is_dir()):
        raise E.InstallError("EXACT_PRIVATE_PREFLIGHT_SCOPE_REQUIRED")
    E._path(root, stage.relative_to(root).as_posix())
    report_raw = E._read(stage / "report.json")
    if E.sha(report_raw) != payload["preflight_report_sha256"]:
        raise E.InstallError("PRIVATE_PREFLIGHT_REPORT_DRIFT")
    report = json.loads(report_raw)
    if (report.get("candidate_verification") != "PASS" or report["candidate_files"] != plan["files"]
            or report["system_inventory"] != plan["system_inventory"]):
        raise E.InstallError("PRIVATE_PREFLIGHT_PLAN_MISMATCH")
    files = {name: E._read(E._path(stage / "candidate_root", name)) for name in plan["files"]}
    E._validate(plan, files, evidence, datetime.now(timezone.utc).timestamp(), root,
                testing=test_root is not None, phase=_phase(operation))
    if plan.get("homepage_policy"):
        E.verify_routing_sources(json.loads(evidence["routing"]), root=root)
    transaction = json.loads(evidence["transaction"])
    request = json.loads(evidence["request"])
    expected = {"task_id": plan["task_id"], "request_sha256": E.sha(evidence["request"]),
        "transaction_id": plan["transaction_id"], "run_id": transaction["run_id"],
        "manifest_sha256": E.sha(evidence["manifest"])}
    if any(payload.get(key) != value for key, value in expected.items()):
        raise E.InstallError("REMOTE_OPERATION_CANONICAL_BINDING_MISMATCH")
    package = Path(__file__).resolve().parent
    if set(payload.get("remote_package_sha256", {})) != E.MODULES | {"remote_adapter.py", "install_package.py"}:
        raise E.InstallError("EXACT_REMOTE_PACKAGE_CLOSURE_REQUIRED")
    for name, digest in payload["remote_package_sha256"].items():
        E._hash(digest)
        if E.sha(E._read(E._path(package, name))) != digest:
            raise E.InstallError("REMOTE_REVIEWED_PACKAGE_DRIFT")
    for name in E.MODULES:
        if E.sha(E._read(E._path(package, name))) != E.sha(files[name]):
            raise E.InstallError("REMOTE_RUNTIME_NOT_EXACT_PREFLIGHT_MODULE:" + name)
    if operation != "backup" and transaction.get("backup_manifest_sha256") != payload.get("backup_manifest_sha256"):
        raise E.InstallError("REAL_CANONICAL_BACKUP_BINDING_REQUIRED")
    return payload, plan, files, evidence, root


def _locked(root):
    lock = os.open(E._path(root, ".ua_art_publish_transaction.lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock
    except BaseException:
        os.close(lock)
        raise


def _release(lock):
    fcntl.flock(lock, fcntl.LOCK_UN)
    os.close(lock)


def backup(plan, files, evidence, root):
    lock = _locked(root)
    conn = sqlite3.connect(root / "crm.db", timeout=0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if E.database_snapshot(conn) != plan["database"] or E.system_inventory(root) != plan["system_inventory"]:
            raise E.InstallError("PREPARING_BACKUP_CURRENT_SNAPSHOT_DRIFT")
        schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        if E.sha(E.encoded(schema)) != plan["schema_sha256"]:
            raise E.InstallError("PREPARING_BACKUP_SCHEMA_DRIFT")
        quota = json.loads(evidence["quota"])
        db_size = (root / "crm.db").stat().st_size
        needed = 3 * (db_size + sum(v["bytes"] for v in plan["system_inventory"].values())
                       + sum(len(data) for data in files.values())) + 1024 * 1024
        if quota["used_bytes"] + needed > quota["limit_bytes"] * .8 or shutil.disk_usage(root).free < needed:
            raise E.InstallError("PREPARING_FULL_BACKUP_QUOTA_INSUFFICIENT")
        directory = E._path(root, "rezerv_publikacii/TASK088_STAGE3_PREPARING/" + plan["transaction_id"])
        directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.mkdir(mode=0o700)
        for name, expected in plan["system_inventory"].items():
            E._backup_file(E._path(root, name), E._path(directory / "full", name), expected)
        dest_path = directory / "crm.sqlite"
        source = sqlite3.connect((root / "crm.db").as_uri() + "?mode=ro", uri=True, timeout=0)
        dest = sqlite3.connect(dest_path)
        try:
            source.backup(dest)
            if E.database_snapshot(dest) != plan["database"]:
                raise E.InstallError("PREPARING_SQLITE_BACKUP_READBACK_FAILED")
        finally:
            dest.close()
            source.close()
        os.chmod(dest_path, 0o600)
        descriptor = os.open(dest_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        E._atomic(directory / "schema.json", E.encoded(schema))
        manifest = {"contract": "TASK088-STAGE3-FULL-BACKUP-1", "task_id": plan["task_id"],
            "transaction_id": plan["transaction_id"], "install_files_sha256": plan["manifest_sha256"],
            "database": plan["database"], "schema_sha256": plan["schema_sha256"],
            "system_inventory": plan["system_inventory"], "crm_backup_sha256": E._stream_entry(dest_path)["sha256"]}
        E._atomic(directory / "manifest.json", E.encoded(manifest))
        if E.system_inventory(root) != plan["system_inventory"] or E.database_snapshot(conn) != plan["database"]:
            raise E.InstallError("PREPARING_BACKUP_PROTECTED_DRIFT")
        return {"status": "BACKUP_PASS", "backup_manifest_sha256": E.sha(E.encoded(manifest)),
                "backup_directory": str(directory), "database_unchanged": True, "live_files_written": False}
    finally:
        conn.rollback()
        conn.close()
        _release(lock)


def _backup_read(plan, root, expected):
    directory = E._path(root, "rezerv_publikacii/TASK088_STAGE3_PREPARING/" + plan["transaction_id"])
    raw = E._read(directory / "manifest.json")
    if E.sha(raw) != expected:
        raise E.InstallError("IMMUTABLE_CANONICAL_BACKUP_HASH_MISMATCH")
    manifest = json.loads(raw)
    if (manifest["task_id"] != plan["task_id"] or manifest["transaction_id"] != plan["transaction_id"]
            or manifest["system_inventory"] != plan["system_inventory"]
            or manifest["install_files_sha256"] != plan["manifest_sha256"]
            or manifest.get("database") != plan["database"]
            or manifest.get("schema_sha256") != plan["schema_sha256"]):
        raise E.InstallError("CANONICAL_BACKUP_SCOPE_MISMATCH")
    # A correctly bound descriptor is insufficient if its recovery bytes later
    # changed. Independently verify the complete recovery point before OPEN or
    # a restore; none of these reads writes or replaces the CRM database.
    if E.sha(E._read(directory / "schema.json")) != plan["schema_sha256"]:
        raise E.InstallError("CANONICAL_BACKUP_SCHEMA_CORRUPTED")
    database_path = directory / "crm.sqlite"
    if E._stream_entry(database_path)["sha256"] != manifest.get("crm_backup_sha256"):
        raise E.InstallError("CANONICAL_BACKUP_DATABASE_CORRUPTED")
    database = sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True, timeout=0)
    try:
        database.execute("PRAGMA query_only=ON")
        database.execute("BEGIN")
        schema = database.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        if (E.database_snapshot(database) != plan["database"]
                or E.sha(E.encoded(schema)) != plan["schema_sha256"]):
            raise E.InstallError("CANONICAL_BACKUP_DATABASE_READBACK_FAILED")
    finally:
        database.close()
    for name, original in manifest["system_inventory"].items():
        observed = E._stream_entry(E._path(directory / "full", name))
        if any(observed[key] != original[key] for key in ("bytes", "sha256")):
            raise E.InstallError("CANONICAL_BACKUP_FILE_CORRUPTED:" + name)
    return directory, manifest


def verify(plan, files, root):
    lock = _locked(root)
    conn = sqlite3.connect((root / "crm.db").as_uri() + "?mode=ro", uri=True, timeout=0)
    try:
        conn.execute("PRAGMA query_only=ON")
        expected = dict(plan["system_inventory"])
        for name, data in files.items():
            expected[name] = {"sha256": E.sha(data), "bytes": len(data),
                "mode": expected.get(name, {}).get("mode", 0o644 if name.endswith(".html") else 0o600)}
        if E.system_inventory(root) != expected or E.database_snapshot(conn) != plan["database"]:
            raise E.InstallError("INSTALLED_SYSTEM_OR_CRM_READBACK_FAILED")
        if E.sha(E.encoded(conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall())) != plan["candidate_schema_sha256"]:
            raise E.InstallError("INSTALLED_SCHEMA_READBACK_FAILED")
        receipt = json.loads(E._read(root / "rezerv_publikacii/TASK088_STAGE3" / plan["transaction_id"] / "install_receipt.json"))
        if (receipt.get("status") != "INSTALLED_PENDING_LIVE_ACCEPTANCE" or receipt.get("stage3_complete") is not False
                or receipt.get("transaction_id") != plan["transaction_id"] or receipt.get("task_id") != plan["task_id"]
                or receipt.get("installed_files_sha256") != {name: E.sha(value) for name, value in files.items()}):
            raise E.InstallError("ACTUAL_INSTALL_RECEIPT_REQUIRED")
        return {"status": "INSTALLATION_VERIFIED", "database_unchanged": True,
                "protected_files_unchanged": True, "source_and_schema": "PASS", "independent_readback": "PASS",
                "install_receipt": receipt, "stage3_complete": False, "bot_restarted": False}
    finally:
        conn.close()
        _release(lock)


def rollback(plan, files, root, backup_sha):
    directory, manifest = _backup_read(plan, root, backup_sha)
    lock = _locked(root)
    conn = sqlite3.connect(root / "crm.db", timeout=0)
    changed = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        initial_db = E.database_snapshot(conn)
        initial_inventory = E.system_inventory(root)
        originals = {}
        conflicts = []
        for name, candidate in files.items():
            path = E._path(root, name)
            before = plan["files"][name]["before_sha256"]
            original = E._read(E._path(directory / "full", name)) if before is not None else None
            if (E.sha(original) if original is not None else None) != before:
                raise E.InstallError("ROLLBACK_BACKUP_PREIMAGE_MISMATCH")
            current = E._read(path) if path.exists() else None
            if current != original and current != candidate:
                conflicts.append(name)
            originals[name] = original
        if conflicts:
            raise E.InstallError("ROLLBACK_FOREIGN_WRITE_CONFLICT:" + ",".join(conflicts))
        before_schema = json.loads(E._read(directory / "schema.json"))
        current_schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        schema_before_set = {tuple(row) for row in before_schema}
        if any(tuple(row) not in current_schema for row in before_schema):
            raise E.InstallError("ROLLBACK_EXISTING_SCHEMA_DRIFT_PRESERVED")
        added = [row for row in current_schema if row not in schema_before_set]
        if any(row[2] not in E.SCHEMA_TABLES for row in added):
            raise E.InstallError("ROLLBACK_FOREIGN_SCHEMA_PRESERVED")
        new_tables = [row[1] for row in added if row[0] == "table"]
        for table in new_tables:
            if conn.execute('SELECT 1 FROM "' + table + '" LIMIT 1').fetchone():
                raise E.InstallError("ROLLBACK_ACTIVE_OPERATIONS_OR_AUDIT_PRESERVED")
        for table in new_tables:
            conn.execute('DROP TABLE "' + table + '"')
        if E.sha(E.encoded(conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall())) != plan["schema_sha256"]:
            raise E.InstallError("ROLLBACK_EXACT_ORIGINAL_SCHEMA_REQUIRED")
        for name in reversed(sorted(files)):
            path = E._path(root, name)
            original = originals[name]
            current = E._read(path) if path.exists() else None
            if current == original:
                continue
            if current != files[name]:
                raise E.InstallError("ROLLBACK_CAS_DRIFT")
            changed.append(name)
            if original is None:
                path.unlink()
                E._fsync_dir(path.parent)
            else:
                E._atomic(path, original, manifest["system_inventory"][name]["mode"])
        expected_inventory = dict(initial_inventory)
        for name, original in originals.items():
            if original is None:
                expected_inventory.pop(name, None)
            else:
                expected_inventory[name] = manifest["system_inventory"][name]
        if E.system_inventory(root) != expected_inventory:
            raise E.InstallError("ROLLBACK_PROTECTED_SYSTEM_READBACK_FAILED")
        if E.database_snapshot(conn) != initial_db:
            raise E.InstallError("ROLLBACK_CHANGED_CURRENT_CRM_VALUES")
        conn.commit()
        separate = sqlite3.connect((root / "crm.db").as_uri() + "?mode=ro", uri=True)
        try:
            separate.execute("PRAGMA query_only=ON")
            if (E.database_snapshot(separate) != initial_db
                    or E.system_inventory(root) != expected_inventory):
                raise E.InstallError("ROLLBACK_INDEPENDENT_DB_READBACK_FAILED")
        finally:
            separate.close()
        return {"status": "ROLLED_BACK", "restored": True, "database_unchanged": True,
                "protected_files_unchanged": True, "live_verify": "PASS", "bot_restarted": False}
    except BaseException as exc:
        conn.rollback()
        if changed:
            raise E.InstallError("ROLLBACK_INTERRUPTED_RECONCILIATION_REQUIRED") from exc
        raise
    finally:
        conn.close()
        _release(lock)


def run(operation_plan, *, test_root=None, expected_payload_sha256=None):
    payload, plan, files, evidence, root = load_operation(operation_plan, test_root=test_root,
        expected_payload_sha256=expected_payload_sha256)
    operation = payload["operation"]
    if operation == "backup":
        result = backup(plan, files, evidence, root)
    else:
        _backup_read(plan, root, payload["backup_manifest_sha256"])
        if operation == "execute":
            import uaart_price_sync_runtime as runtime
            installed = E.install(plan, files, evidence, expected_plan_sha256=E.sha(E.encoded(plan)),
                                  schema_installer=runtime.install, test_root=test_root)
            result = {"status": "INSTALLED_AWAITING_VERIFICATION", "install_receipt": installed,
                      "stage3_complete": False, "bot_restarted": False}
        elif operation == "verify":
            result = verify(plan, files, root)
        else:
            result = rollback(plan, files, root, payload["backup_manifest_sha256"])
    return {**{key: payload[key] for key in BINDINGS}, **result,
        "operation": operation, "backup_manifest_sha256": result.get("backup_manifest_sha256", payload.get("backup_manifest_sha256")),
        "live_price_writes": False, "stage1_reinstalled": False, "stage2_reinstalled": False,
        "public_acceptance": "NOT_RUN", "telegram_acceptance": "NOT_RUN"}


def operation_claim(raw):
    """Bind the one-shot barrier to immutable input and reviewed executor bytes."""
    payload = json.loads(raw)
    operation = payload.get("operation")
    if operation not in ("backup", "execute", "verify", "rollback"):
        raise E.InstallError("EXACT_REMOTE_OPERATION_REQUIRED")
    if any(not isinstance(payload.get(key), str) or not payload[key] for key in BINDINGS):
        raise E.InstallError("REMOTE_OPERATION_IDENTITY_REQUIRED")
    adapter_sha = payload.get("remote_package_sha256", {}).get("remote_adapter.py")
    if adapter_sha != E.sha(E._read(Path(__file__))):
        raise E.InstallError("REMOTE_EXECUTOR_SOURCE_DRIFT")
    return {"contract": "TASK088-REMOTE-OPERATION-CLAIM-1",
        **{key: payload[key] for key in BINDINGS}, "operation": operation,
        "payload_sha256": E.sha(raw), "adapter_sha256": adapter_sha}


def _write_new(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    E._fsync_dir(path.parent)


def _publish_result(path, result):
    # Never expose a partly written result to the controller. No replacement of
    # an earlier result is permitted, including a result left by a lost reply.
    descriptor, temporary = tempfile.mkstemp(prefix=".operation-result-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(E.encoded(result))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        E._fsync_dir(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _completion(claim):
    return {"contract": "TASK088-REMOTE-OPERATION-RETURN-1",
        "payload_sha256": claim["payload_sha256"], "claim_sha256": E.sha(E.encoded(claim)),
        "adapter_sha256": claim["adapter_sha256"], "operation_returned": True}


def _predecessor_terminal(directory, operation, current, backup_sha):
    """Read a real same-run result; a claim/launch or failure is insufficient."""
    try:
        claim = operation_claim(E._read(directory / (operation + "-plan.json")))
        result = json.loads(E._read(directory / (operation + "-result.json")))
        actual_claim = E._read(directory / (operation + "-claim.json"))
    except (OSError, ValueError) as exc:
        raise E.InstallError("PREDECESSOR_TERMINAL_RECONCILIATION_REQUIRED:" + operation) from exc
    expected_status = {"backup": "BACKUP_PASS", "execute": "INSTALLED_AWAITING_VERIFICATION",
                       "verify": "INSTALLATION_VERIFIED"}[operation]
    if (claim["operation"] != operation or actual_claim != E.encoded(claim)
            or any(claim[key] != current[key] or result.get(key) != current[key] for key in BINDINGS)
            or result.get("operation") != operation or result.get("status") != expected_status
            or result.get("execution") != _completion(claim)
            or result.get("backup_manifest_sha256") != backup_sha
            or result.get("live_price_writes") is not False or result.get("stage1_reinstalled") is not False
            or result.get("stage2_reinstalled") is not False or result.get("public_acceptance") != "NOT_RUN"
            or result.get("telegram_acceptance") != "NOT_RUN"):
        raise E.InstallError("PREDECESSOR_TERMINAL_RECONCILIATION_REQUIRED:" + operation)


def _admit_operation(directory, claim, payload):
    """Order effects under one run mutex; rollback permanently closes forward admission."""
    operation = claim["operation"]
    if operation != "rollback" and any((directory / ("rollback" + suffix)).exists()
            for suffix in ("-plan.json", "-launch.json", "-claim.json", "-result.json")):
        raise E.InstallError("ROLLBACK_BARRIER_FORWARD_EXECUTION_FORBIDDEN")
    if operation == "backup":
        if any((directory / (other + suffix)).exists() for other in ("execute", "verify")
               for suffix in ("-claim.json", "-result.json")):
            raise E.InstallError("FORWARD_OPERATION_ALREADY_ADMITTED")
        return
    backup_sha = payload.get("backup_manifest_sha256")
    E._hash(backup_sha)
    _predecessor_terminal(directory, "backup", claim, backup_sha)
    if operation == "verify":
        _predecessor_terminal(directory, "execute", claim, backup_sha)
    elif operation == "rollback":
        # A queued provider request may not have started yet. Its uploaded plan
        # or launch intent is already an unresolved predecessor. The rollback
        # claim was fsynced under our mutex before reaching this check, so a
        # delayed forward runner cannot execute after this rollback admission.
        for previous in ("execute", "verify"):
            if any((directory / (previous + suffix)).exists()
                   for suffix in ("-plan.json", "-launch.json", "-claim.json", "-result.json")):
                _predecessor_terminal(directory, previous, claim, backup_sha)


def run_once(operation_plan, *, test_root=None):
    """Serialize every operation in this exact run, including admission/result writes."""
    path = Path(operation_plan)
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise E.InstallError("REMOTE_OPERATION_SYMLINK_FORBIDDEN")
    descriptor = os.open(path.parent / ".operation-session.lock",
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise E.InstallError("REGULAR_OPERATION_SESSION_LOCK_REQUIRED")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise E.InstallError("REMOTE_OPERATION_IN_FLIGHT_RECONCILIATION_REQUIRED") from exc
        return _run_once_locked(path, test_root=test_root)
    finally:
        os.close(descriptor)


def _run_once_locked(path, *, test_root=None):
    """At most one protected invocation, even after provider automatic restart.

    A durable claim without a result is UNKNOWN, never a retry permit. Claims
    are not leases and cannot expire. This is separate from canonical admission:
    run/load_operation still validate all live gates before any protected work.
    """
    raw = E._read(path)
    claim = operation_claim(raw)
    operation = claim["operation"]
    if path.name != operation + "-plan.json":
        raise E.InstallError("EXACT_OPERATION_PLAN_NAME_REQUIRED")
    output = path.with_name(operation + "-result.json")
    claim_path = path.with_name(operation + "-claim.json")
    claim_raw = E.encoded(claim)
    completion = _completion(claim)
    try:
        _write_new(claim_path, claim_raw)
    except FileExistsError:
        if E._read(claim_path) != claim_raw:
            raise E.InstallError("REMOTE_OPERATION_CLAIM_DRIFT")
        if not output.exists():
            raise E.InstallError("REMOTE_OPERATION_CLAIMED_RECONCILIATION_REQUIRED")
        result = json.loads(E._read(output))
        if (result.get("execution") != completion or result.get("operation") != operation
                or any(result.get(key) != claim[key] for key in BINDINGS)):
            raise E.InstallError("REMOTE_TERMINAL_RESULT_RECONCILIATION_REQUIRED")
        return result  # Readback only; never re-enter an already claimed run.
    if output.exists():
        raise E.InstallError("UNCLAIMED_EXISTING_RESULT_RECONCILIATION_REQUIRED")
    # Detect altered input after the durable barrier, before calling the engine.
    if E._read(path) != raw:
        raise E.InstallError("REMOTE_OPERATION_PLAN_DRIFT")
    try:
        _admit_operation(path.parent, claim, json.loads(raw))
        result = run(path, test_root=test_root, expected_payload_sha256=E.sha(raw))
    except Exception as exc:
        # Failure is evidence, not terminal/coherent-state authority. In
        # particular a failed finally block must not authorize runner deletion.
        result = {**{key: claim[key] for key in BINDINGS}, "operation": operation,
            "status": "FAIL", "error_type": type(exc).__name__,
            "error": str(exc) if isinstance(exc, E.InstallError) else type(exc).__name__,
            "execution": {**completion, "operation_returned": False}}
    else:
        result = {**result, "execution": completion}
    _publish_result(output, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    result = run_once(args.plan)
    output = Path(args.plan).with_name(result["operation"] + "-result.json")
    print(json.dumps({"status": result["status"], "output": str(output)}))
    return 0 if result["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
