"""Hash-bound remote phase owner; import/default CLI never contacts production.

Each phase owns a bounded watchdog and its own pause/resume interval. Backup
resumes the baseline; execute consumes the original immutable backup under a
fresh source/data CAS; rollback preserves the current database. The transport
uploads a fresh private stage for each phase. No credentials are persisted or
passed in command arguments.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import sqlite3
import stat
import subprocess
import sys
import time

TASK = "UA-ART-CRM-DELETE-RECOVERY-002-INSTALL"
PARENT_TASK = "UA-ART-CRM-DELETE-RECOVERY-002"
SCOPE = "INSTALLATION_AND_RUNTIME_HTTP_VERIFY"
TRANSPORT_SCHEMA = "ua-art-crm-delete-recovery-002-transport-v1"
RECEIPT_SCHEMA = "ua-art-crm-delete-recovery-002-remote-receipt-v1"
ORIGIN = "https://github.com/art20021986-wq/ua-art-autopilot.git"
SOURCES = ("remote_worker.py", "lifecycle_controller.py", "lifecycle_worker.py", "package_install.py", "watchdog.py")
HEX = re.compile(r"[0-9a-f]{64}")
OPERATIONS = frozenset({"backup", "execute", "rollback"})


def require(value, code):
    if not value:
        raise RuntimeError(code)


def safe_error_code(exc):
    value = str(exc)
    return value if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", value) else type(exc).__name__


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def wire_encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


receipt_bytes = wire_encoded


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(path, *, exists=True):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=exists) == path and not path.is_symlink(), "CANONICAL_PATH_REQUIRED")
    return path


def private_root(path):
    path = canonical(path)
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
            "PRIVATE_STAGE_REQUIRED")
    return path


def bounded_read(path, expected=None, *, normalize=False):
    path = canonical(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                (info.st_mode & (0o022 if normalize else 0o077)) == 0,
                "PRIVATE_REGULAR_INPUT_REQUIRED")
        require(info.st_size <= 8 * 1024 * 1024, "INPUT_SIZE_BOUND")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        after = os.fstat(fd)
        require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) and
                len(raw) == info.st_size, "INPUT_CHANGED_DURING_READ")
        if expected is not None:
            require(HEX.fullmatch(str(expected)) and sha(raw) == expected, "INPUT_HASH_MISMATCH")
        if normalize:
            require(expected is not None and path.stat(follow_symlinks=False).st_ino == info.st_ino,
                    "HASH_VERIFIED_UPLOAD_REQUIRED")
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        return raw
    finally:
        os.close(fd)


def relative_file(root, name):
    require(type(name) is str and name == str(PurePosixPath(name)) and not name.startswith("/") and
            ".." not in PurePosixPath(name).parts and name not in ("", "."), "CANONICAL_RELATIVE_INPUT_REQUIRED")
    path = canonical(root / name)
    require(path.is_relative_to(root), "STAGE_PATH_ESCAPE")
    return path


def normalize_credential(*, recovery=False):
    """Use PythonAnywhere's native task environment; never return its value."""
    native = os.environ.get("API_TOKEN")
    inherited = os.environ.get("PYTHONANYWHERE_API_TOKEN")
    if recovery and not native:
        require(isinstance(inherited, str) and bool(inherited.strip()), "RECOVERY_PROVIDER_CREDENTIAL_MISSING")
        return
    require(isinstance(native, str) and bool(native.strip()) and "\x00" not in native, "NATIVE_API_TOKEN_MISSING")
    require(not inherited or inherited == native, "PROVIDER_CREDENTIAL_ENVIRONMENT_CONFLICT")
    os.environ["PYTHONANYWHERE_API_TOKEN"] = native


class TransportContext:
    def __init__(self, path, digest, operation=None, *, own_source=None):
        self.path = canonical(path)
        self.sha256 = digest
        private_root(self.path.parent)
        self.value = value = json.loads(bounded_read(self.path, digest, normalize=True))
        required = {"schema", "task_id", "workflow_run_id", "transaction_id", "request_sha256", "manifest_sha256",
                    "operation", "stage", "files", "parameters"}
        require(isinstance(value, dict) and set(value) == required and value["schema"] == TRANSPORT_SCHEMA and
                value["task_id"] == TASK and value["operation"] in OPERATIONS and
                (operation is None or operation == value["operation"]), "EXACT_TRANSPORT_CONTEXT_REQUIRED")
        self.operation = value["operation"]
        self.root = private_root(value["stage"])
        require(self.path.parent == self.root, "TRANSPORT_CONTEXT_STAGE_BINDING")
        for key in ("request_sha256", "manifest_sha256"):
            require(HEX.fullmatch(str(value[key])), "TRANSPORT_DIGEST_REQUIRED")
        require(type(value["workflow_run_id"]) is str and re.fullmatch(r"[0-9]{1,30}", value["workflow_run_id"]) and
                type(value["transaction_id"]) is str and re.fullmatch(r"tx-[A-Za-z0-9._-]{16,120}", value["transaction_id"]),
                "WORKFLOW_IDENTITY_REQUIRED")
        files = value["files"]
        require(isinstance(files, dict) and set(SOURCES) <= set(files) and 5 <= len(files) <= 250,
                "COMPLETE_BOUNDED_FILE_BINDING_REQUIRED")
        self.pins = {}
        for name, file_sha in files.items():
            file = relative_file(self.root, name)
            require(file != self.path and file.name not in {"watchdog-context.json", "watchdog-ready.json", "watchdog-result.json",
                    "watchdog-terminal.json", "phase-journal.json", "phase.lock"} and
                    not file.name.startswith(("result-", "completed-")), "RESERVED_PHASE_PATH")
            bounded_read(file, file_sha, normalize=True)
            self.pins[file] = file_sha
        require(canonical(own_source or Path(__file__).absolute()) == self.root / "remote_worker.py", "STAGED_ENTRYPOINT_REQUIRED")
        params = value["parameters"]
        require(isinstance(params, dict) and set(params) == {"plan_path", "plan_sha256", "installation_policy_sha256", "backup_manifest_sha256"},
                "EXACT_PHASE_PARAMETERS_REQUIRED")
        self.plan_path = canonical(params["plan_path"])
        require(self.plan_path.is_relative_to(self.root) and self.pins.get(self.plan_path) == params["plan_sha256"],
                "PLAN_FILE_BINDING")
        self.plan = plan = json.loads(bounded_read(self.plan_path, params["plan_sha256"]))
        require(plan.get("version") == 1 and plan.get("task_id") == TASK and plan.get("parent_task_id") == PARENT_TASK and
                plan.get("acceptance_scope") == SCOPE and plan.get("installation_policy_sha256") == params["installation_policy_sha256"] and
                HEX.fullmatch(str(params["installation_policy_sha256"])), "CHILD_INSTALLATION_POLICY_REQUIRED")
        require(type(plan.get("maximum_seconds")) is int and 60 <= plan["maximum_seconds"] <= 1200, "BOUNDED_OWNER_LIFETIME_REQUIRED")
        require(isinstance(plan.get("package_sources"), dict) and set(SOURCES) <= set(plan["package_sources"]), "COMPLETE_EXECUTABLE_PINS_REQUIRED")
        for name in SOURCES:
            require(plan["package_sources"][name] == files[name], "PLAN_EXECUTABLE_PIN_MISMATCH")
        self.manifest_path = relative_file(self.root, plan["package_manifest_path"])
        require(self.pins.get(self.manifest_path) == plan["package_manifest_sha256"], "STAGED_PACKAGE_MANIFEST_BINDING")
        authority = plan["authority"]
        require(authority["request_sha256"] == value["request_sha256"] and
                str(authority["run_id"]) == value["workflow_run_id"] and authority["transaction_id"] == value["transaction_id"],
                "PHASE_AUTHORITY_IDENTITY")
        self.backup_sha256 = params["backup_manifest_sha256"]
        require(self.backup_sha256 is None if self.operation == "backup" else bool(HEX.fullmatch(str(self.backup_sha256))),
                "ORIGINAL_BACKUP_PHASE_BINDING")

    def revalidate(self):
        private_root(self.root)
        bounded_read(self.path, self.sha256)
        for path, digest in self.pins.items():
            bounded_read(path, digest)

    def identity(self):
        return {key: self.value[key] for key in ("task_id", "workflow_run_id", "transaction_id", "request_sha256", "manifest_sha256", "operation")}


def checkout_authority(context, *, run=subprocess.run):
    """Read-only public-origin checkout; no credential inheritance or hooks."""
    authority = context.plan["authority"]
    expected = authority["main_commit"]
    require(type(expected) is str and re.fullmatch(r"[0-9a-f]{40}", expected), "EXACT_AUTHORITY_COMMIT_REQUIRED")
    require(authority.get("repository_root") == "authority", "STAGE_RELATIVE_AUTHORITY_ROOT_REQUIRED")
    target = context.root / "authority"
    require(not target.exists() and not target.is_symlink(), "FRESH_AUTHORITY_CHECKOUT_REQUIRED")
    target.mkdir(mode=0o700)
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_ASKPASS": "/bin/false"}
    prefix = ["git", "-c", "credential.helper=", "-c", "core.hooksPath=/dev/null"]
    def command(args):
        result = run(prefix + args, cwd=context.root, env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=90, check=False)
        require(result.returncode == 0 and len(result.stdout) <= 4096, "PUBLIC_AUTHORITY_CHECKOUT_FAILED")
        return result.stdout.decode().strip()
    command(["clone", "--depth", "1", "--single-branch", "--branch", "main", "--no-tags", ORIGIN, str(target)])
    require(command(["-C", str(target), "rev-parse", "HEAD"]) == expected, "AUTHORITY_CHECKOUT_HEAD_MISMATCH")
    require(command(["-C", str(target), "remote", "get-url", "origin"]) == ORIGIN, "AUTHORITY_ORIGIN_MISMATCH")
    require(command(["-C", str(target), "ls-remote", "origin", "refs/heads/main"]).split() ==
            [expected, "refs/heads/main"], "AUTHORITY_REMOTE_HEAD_MISMATCH")
    plan = copy.deepcopy(context.plan)
    plan["authority"]["repository_root"] = str(target)
    source_commit = authority.get("code_source_commit", expected)
    require(type(source_commit) is str and re.fullmatch(r"[0-9a-f]{40}", source_commit), "EXACT_CODE_SOURCE_COMMIT_REQUIRED")
    if context.operation != "rollback":
        require(authority.get("source_repository_root", "authority") == "authority" and source_commit == expected,
                "NEW_PHASE_REQUIRES_CURRENT_AUTHORITY_SOURCE")
        plan["authority"]["source_repository_root"] = str(target)
    else:
        require(authority.get("source_repository_root") == "source_authority", "PINNED_SOURCE_DIRECTORY_REQUIRED")
        command(["-C", str(target), "fetch", "--depth=256", "origin", "main"])
        command(["-C", str(target), "merge-base", "--is-ancestor", source_commit, expected])
        source = context.root / "source_authority"
        require(not source.exists() and not source.is_symlink(), "FRESH_PINNED_SOURCE_REQUIRED")
        command(["-C", str(target), "worktree", "add", "--detach", str(source), source_commit])
        require(canonical(source).is_dir(), "PINNED_SOURCE_CHECKOUT_REQUIRED")
        source.chmod(0o700)
        require(command(["-C", str(source), "rev-parse", "HEAD"]) == source_commit, "PINNED_SOURCE_HEAD_MISMATCH")
        claim_rel = "state/claims/%s.%s.%s.json" % (TASK, authority["request_sha256"], authority["run_id"])
        def repo_raw(name):
            path = relative_file(target, name)
            require(path.suffix == ".json" and path.stat().st_size <= 2 * 1024 * 1024 and
                    stat.S_ISREG(path.stat().st_mode), "DURABLE_AUTHORITY_DOCUMENT_REQUIRED")
            return path.read_bytes()
        claim = json.loads(repo_raw(claim_rel))
        request = json.loads(repo_raw(authority["request_path"]))
        paths = (claim_rel, claim["production_transaction_path"], authority["request_path"],
                 claim["autostart_ledger_path"], request["execution"]["backup_receipt_path"])
        require(len(set(paths)) == 5, "EXACT_FIVE_DURABLE_DOCUMENTS_REQUIRED")
        from package_install import atomic
        for name in paths:
            raw = repo_raw(name)
            require(PurePosixPath(name).parts[0] in ("state", "tasks"), "DURABLE_DOCUMENT_SCOPE")
            destination = source / name
            require(destination.resolve(strict=False) == destination, "PINNED_OVERLAY_SYMLINK_REFUSED")
            destination.parent.mkdir(parents=True, exist_ok=True)
            atomic(destination, raw)
        plan["authority"]["source_repository_root"] = str(source)
    return plan


class OwnedTriggerAPI:
    """Exclude only this exact authenticated transport trigger from inventory."""
    def __init__(self, api, context, *, recovery=False, expected_id=None, command_reader=None):
        self.api, self.context, self.recovery = api, context, recovery
        self.argv = ["python3.10", "-I", "-B", str(context.root / "remote_worker.py"), "--context", str(context.path),
                     "--context-sha256", context.sha256, "--operation", context.operation]
        self.command = shlex.join(self.argv)
        self.description = TASK + " " + context.operation
        self.id = expected_id
        if not recovery:
            reader = command_reader or (lambda: Path("/proc/self/cmdline").read_bytes())
            actual = [part.decode() for part in reader().rstrip(b"\x00").split(b"\x00")]
            require(bool(actual), "OWNED_TRIGGER_PROCESS_REQUIRED")
            actual[0] = Path(actual[0]).name
            require(actual == self.argv, "OWNED_TRIGGER_PROCESS_COMMAND")
        self._filter(self.api.request("GET", "always_on/"))

    def _filter(self, value):
        key = None
        if isinstance(value, dict):
            key = next((name for name in ("results", "objects", "tasks") if name in value), None)
            require(key is not None, "PROVIDER_TRIGGER_LIST_SHAPE")
            rows = value[key]
        else:
            rows = value
        require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "PROVIDER_TRIGGER_LIST_SHAPE")
        matches = [row for row in rows if row.get("command") == self.command and row.get("description") == self.description]
        require(len(matches) == 1 and type(matches[0].get("id")) is int and matches[0]["id"] > 0 and
                matches[0].get("enabled") is True, "EXACT_OWNED_TRIGGER_REQUIRED")
        row = matches[0]
        require(isinstance(row.get("state"), str) and bool(row["state"]) and
                (self.recovery or row["state"].lower() == "running"), "OWNED_TRIGGER_STATE")
        require(self.id is None or row["id"] == self.id, "OWNED_TRIGGER_ID_CHANGED")
        self.id = row["id"]
        filtered = [item for item in rows if item is not row]
        return dict(value, **{key: filtered}) if key else filtered

    def request(self, method, endpoint, fields=None):
        result = self.api.request(method, endpoint, fields)
        return self._filter(result) if (method, endpoint) == ("GET", "always_on/") else result

    def supervisor(self):
        return self.api.supervisor()

    def set_enabled(self, enabled):
        return self.api.set_enabled(enabled)

    def reload(self):
        return self.api.reload()


def current_evidence(worker, *, installed):
    from package_install import application_data, application_schema, fingerprint, relative
    verified = worker.verify_images(installed=installed)
    expected, observed = {}, {}
    for name, item in worker.package.files.items():
        expected[name] = item["payload_sha256"] if installed else item["before_sha256"]
    config = worker.package.runtime_config
    if installed:
        expected[config["destination"]] = config["payload_sha256"]
    for name in expected:
        observed[name] = fingerprint(relative(worker.root, name))
    expected[worker.wsgi.item["destination"]] = worker.wsgi.item["payload_sha256"] if installed else worker.wsgi.item["before_sha256"]
    observed[worker.wsgi.item["destination"]] = fingerprint(worker.wsgi.path)
    require(expected == observed, "PHASE_FILE_READBACK_MISMATCH")
    guards = worker.package.manifest["source_guards"]
    guarded = {name: fingerprint(relative(worker.root, name)) for name in guards}
    require(guarded == guards, "PHASE_GUARDED_SOURCE_MISMATCH")
    with closing(worker.transaction._connect(readonly=True)) as conn:
        conn.execute("BEGIN")
        require(conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "PHASE_DATABASE_INTEGRITY")
        require(application_schema(conn) == worker.package.manifest["application_schema_sha256"], "PHASE_APPLICATION_SCHEMA_CHANGED")
        logical = application_data(conn)
    return {"files": {"expected_sha256": expected, "observed_sha256": observed,
                      "guarded_expected_sha256": guards, "guarded_observed_sha256": guarded}, "logical_sha256": logical,
            "application_schema_sha256": worker.package.manifest["application_schema_sha256"], "database_integrity": "ok",
            "deletion_schema_projection": verified["deletion_schema_projection"],
            "deletion_schema_sha256": verified["deletion_schema_sha256"]}


def backup_evidence(worker, digest):
    from package_install import application_data, fingerprint
    worker.verify_existing_backup(digest)
    composite = json.loads(bounded_read(worker.transaction.folder / "phase_backup_manifest.json", digest))
    code, code_sha = worker.transaction._manifest()
    snapshot = worker.transaction.folder / code["database_file"]
    with closing(sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)) as conn:
        require(conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "BACKUP_PROOF_INTEGRITY")
        logical = application_data(conn)
    require(logical == code["database_logical_sha256"], "BACKUP_PROOF_LOGICAL_CHECKSUM")
    return {"manifest": composite, "manifest_sha256": digest, "code_manifest": code, "code_manifest_sha256": code_sha,
            "database": {"snapshot_sha256": fingerprint(snapshot), "logical_sha256": logical,
                         "integrity": "ok", "wal_coherent": True}, "durable": True, "files_verified": True}


def write_terminal_files(root, operation, terminal_path, journal):
    from package_install import atomic
    values = [(terminal_path, encoded(journal["terminal"])),
              (root / ("result-" + operation + ".json"), wire_encoded(journal["receipt"]))]
    if journal["receipt"]["safe_to_stop"]:
        values.append((root / ("completed-" + operation + ".json"), wire_encoded(journal["receipt"])))
    for path, raw in values:
        if path.exists() or path.is_symlink():
            require(bounded_read(path) == raw, "TERMINAL_RECEIPT_CONFLICT")
        else:
            atomic(path, raw)


def terminal_reentry(transport):
    """Always-on restart replays only a durable terminal receipt, no effects."""
    refusal = transport.root / "prepause-refusal.json"
    if refusal.exists():
        receipt = json.loads(bounded_read(refusal))
        require(all(receipt.get(key) == value for key, value in transport.identity().items()) and
                receipt.get("context_sha256") == transport.sha256 and receipt.get("status") == "FAIL" and
                receipt.get("safe_to_stop") is True and receipt.get("no_pause_or_write") is True,
                "PREPAUSE_REFUSAL_BINDING")
        from package_install import atomic
        for prefix in ("result-", "completed-"):
            target = transport.root / (prefix + transport.operation + ".json")
            raw = wire_encoded(receipt)
            if target.exists() or target.is_symlink():
                require(bounded_read(target) == raw, "PREPAUSE_RECEIPT_CONFLICT")
            else:
                atomic(target, raw)
        return receipt
    path = transport.root / "phase-journal.json"
    if not path.exists():
        return None
    journal = json.loads(bounded_read(path))
    require(journal.get("transport_context_sha256") == transport.sha256 and
            journal.get("operation") == transport.operation, "TERMINAL_REENTRY_TRANSPORT_BINDING")
    if journal.get("stage") != "TERMINAL":
        raise RuntimeError("ORIGINAL_OWNER_CONTEXT_REQUIRES_WATCHDOG_RECOVERY")
    watcher = json.loads(bounded_read(transport.root / "watchdog-context.json", journal["context_sha256"]))
    for key in ("owner_pid", "pgid", "start_ticks", "package_manifest_sha256"):
        require(journal.get(key) == watcher.get(key) and journal["terminal"].get(key) == watcher.get(key),
                "TERMINAL_REENTRY_OWNER_BINDING")
    require(journal["terminal"].get("context_sha256") == journal["context_sha256"] and
            watcher.get("lifecycle_plan_path") == str(transport.path) and
            watcher.get("lifecycle_plan_sha256") == transport.sha256 and
            watcher.get("result_path") == str(transport.root / "watchdog-terminal.json"), "TERMINAL_REENTRY_CONTEXT_BINDING")
    receipt = journal["receipt"]
    require(all(receipt.get(key) == value for key, value in transport.identity().items()) and
            receipt.get("context_sha256") == transport.sha256 and
            receipt.get("package_manifest_sha256") == transport.plan["package_manifest_sha256"] and
            receipt.get("installation_policy_sha256") == transport.plan["installation_policy_sha256"] and
            type(receipt.get("safe_to_stop")) is bool, "TERMINAL_REENTRY_RECEIPT_BINDING")
    write_terminal_files(transport.root, transport.operation, Path(watcher["result_path"]), journal)
    return receipt


def prepause_refusal(transport, error_code):
    """A verified stage that never owned a pause can safely stop its trigger."""
    from package_install import atomic
    transport.revalidate()
    journal_path = transport.root / "phase-journal.json"
    if journal_path.exists():
        journal = json.loads(bounded_read(journal_path))
        if journal.get("stage") != "ADMITTED" or journal.get("transport_context_sha256") != transport.sha256:
            return False
    if any((transport.root / (prefix + transport.operation + ".json")).exists() for prefix in ("result-", "completed-")):
        return False
    watcher_path = transport.root / "watchdog-context.json"
    if journal_path.exists() and not watcher_path.exists():
        return False
    if watcher_path.exists():
        raw = bounded_read(watcher_path)
        watcher = json.loads(raw)
        # A supervisor restart is not the old owner. It must not disarm the
        # old owner's watchdog merely because its journal is still ADMITTED.
        ticks = int(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19])
        if watcher.get("owner_pid") != os.getpid() or watcher.get("start_ticks") != ticks:
            return False
        require(watcher.get("lifecycle_plan_path") == str(transport.path) and watcher.get("lifecycle_plan_sha256") == transport.sha256 and
                watcher.get("package_manifest_sha256") == transport.plan["package_manifest_sha256"] and
                watcher.get("result_path") == str(transport.root / "watchdog-terminal.json"), "PREPAUSE_WATCHDOG_BINDING")
        terminal = {"context_sha256": sha(raw), "package_manifest_sha256": watcher["package_manifest_sha256"],
                    **{key: watcher[key] for key in ("owner_pid", "pgid", "start_ticks")},
                    "status": "RECOVERED", "safe_to_stop": True, "no_pause_or_write": True}
        terminal_path = Path(watcher["result_path"])
        if terminal_path.exists() or terminal_path.is_symlink():
            require(json.loads(bounded_read(terminal_path)) == terminal, "PREPAUSE_WATCHDOG_TERMINAL_CONFLICT")
        else:
            atomic(terminal_path, encoded(terminal))
    receipt = {"schema": RECEIPT_SCHEMA, "schema_version": RECEIPT_SCHEMA, **transport.identity(),
               "context_sha256": transport.sha256, "status": "FAIL", "phase_status": "REFUSED_BEFORE_PAUSE",
               "safe_to_stop": True, "no_pause_or_write": True, "watchdog_disarmed": True,
               "execution_origin": "LIVE_REMOTE_READBACK", "scope": SCOPE, "parent_task_id": PARENT_TASK,
               "parent_status": "PENDING_LIVE_TELEGRAM_ACCEPTANCE", "live_telegram_action_verified": False,
               "package_manifest_sha256": transport.plan["package_manifest_sha256"],
               "installation_policy_sha256": transport.plan["installation_policy_sha256"],
               "backup_manifest_sha256": transport.backup_sha256, "unexpected_changes": 0, "error_code": error_code}
    atomic(transport.root / "prepause-refusal.json", wire_encoded(receipt))
    terminal_reentry(transport)
    return True


class PhaseRunner:
    def __init__(self, *, transport, watchdog_context, watchdog_sha256, plan, admission, api, worker,
                 watchdog_ready, inventory=None, probe=None, evidence=current_evidence, backup_proof=backup_evidence,
                 fault=lambda stage: None):
        from lifecycle_controller import provider_inventory, probe_http
        self.transport, self.context, self.context_sha = transport, watchdog_context, watchdog_sha256
        self.plan, self.admission, self.api, self.worker = plan, admission, api, worker
        self.ready, self.inventory, self.probe = watchdog_ready, inventory or provider_inventory, probe or probe_http
        self.evidence, self.backup_proof, self.fault = evidence, backup_proof, fault
        self.operation, self.root = transport.operation, transport.root
        self.path = self.root / "phase-journal.json"
        self.terminal_path = Path(self.context["result_path"])

    def identity(self):
        return {"context_sha256": self.context_sha, "package_manifest_sha256": self.plan["package_manifest_sha256"],
                **{key: self.context[key] for key in ("owner_pid", "start_ticks", "pgid")},
                "transport_context_sha256": self.transport.sha256, "operation": self.operation}

    def save(self, journal, stage, **fields):
        from package_install import atomic
        journal.update(stage=stage, **fields)
        atomic(self.path, encoded(journal))
        self.fault(stage)

    def finish(self, journal, *, success, phase_status, watchdog_status, proofs=None, **extra):
        from package_install import atomic
        proofs = dict(proofs or {})
        if extra.get("no_pause_or_write") and "crm_resume" not in proofs:
            proofs["crm_resume"] = self.api.supervisor()
        resumed = proofs.get("crm_resume", {})
        safe = (resumed.get("id") == 266084 and resumed.get("enabled") is True and
                str(resumed.get("state", "")).lower() == "running" and watchdog_status != "BLOCKED")
        require(not success or safe, "SUCCESS_REQUIRES_CRM_RESUMED_READBACK")
        receipt = {"schema": RECEIPT_SCHEMA, "schema_version": RECEIPT_SCHEMA,
                   **self.transport.identity(), "context_sha256": self.transport.sha256,
                   "status": "PASS" if success else "FAIL", "phase_status": phase_status, "safe_to_stop": safe,
                   "unexpected_changes": 0 if safe else None, "execution_origin": "LIVE_REMOTE_READBACK", "scope": SCOPE,
                   "parent_task_id": PARENT_TASK, "parent_status": "PENDING_LIVE_TELEGRAM_ACCEPTANCE",
                   "live_telegram_action_verified": False, "package_manifest_sha256": self.plan["package_manifest_sha256"],
                   "installation_policy_sha256": self.plan["installation_policy_sha256"],
                   "backup_manifest_sha256": journal.get("backup_manifest_sha256", self.transport.backup_sha256),
                   "proofs": proofs, **extra}
        terminal = {**self.identity(), "status": watchdog_status, "safe_to_stop": safe}
        self.save(journal, "TERMINAL", receipt=receipt, terminal=terminal)
        self._write_terminal(journal)
        return receipt

    def _write_terminal(self, journal):
        write_terminal_files(self.root, self.operation, self.terminal_path, journal)

    def proofs(self, journal, after, http):
        before = journal.get("logical_before", after["logical_sha256"])
        require(before == after["logical_sha256"], "PHASE_APPLICATION_DATA_CHANGED")
        value = {"package_manifest_text": bounded_read(self.transport.manifest_path,
                    self.plan["package_manifest_sha256"]).decode(), "schema_source_text": self.worker.package.schema_source.decode(),
                 "files": after["files"], "http": http,
                 "preservation": {"crm_logical_before": before, "crm_logical_after": after["logical_sha256"],
                    "application_schema_sha256": after["application_schema_sha256"], "database_integrity": after["database_integrity"],
                    "deletion_schema_projection": after["deletion_schema_projection"],
                    "deletion_schema_sha256": after["deletion_schema_sha256"],
                    "public_or_media_writes": 0, "database_restored": False, "code_only": True}}
        digest = journal.get("backup_manifest_sha256")
        if digest:
            value["backup"] = self.backup_proof(self.worker, digest)
        if self.operation == "execute" and "rollback_readiness" in after:
            value["rollback_readiness"] = after["rollback_readiness"]
        return value

    @contextmanager
    def _lock(self):
        # Serializes the provider pause/resume interval across fresh stages.
        path = self.worker.transaction.journal_root / "phase-owner.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def run(self, *, recovery=False):
        with self._lock():
            return self._run(recovery=recovery)

    def _run(self, *, recovery):
        self.transport.revalidate()
        if self.path.exists():
            journal = json.loads(bounded_read(self.path))
            require(all(journal.get(k) == v for k, v in self.identity().items()), "PHASE_JOURNAL_IDENTITY")
            if journal["stage"] == "TERMINAL":
                self._write_terminal(journal)
                return journal["receipt"]
            require(recovery and journal.get("admission", {}).get("status") == "EXISTING_AUTHORITY_PASS", "OWNED_RECOVERY_ONLY")
        else:
            journal = self.identity()
            if recovery:
                return self.finish(journal, success=False, phase_status="NOT_STARTED", watchdog_status="RECOVERED", no_pause_or_write=True)
            admitted = self.admission.check(operation=self.operation)
            require(admitted.get("status") == "EXISTING_AUTHORITY_PASS", "PHASE_ADMISSION_REQUIRED")
            if self.operation != "backup":
                self.worker.verify_existing_backup(self.transport.backup_sha256)
            inventory = self.inventory(self.api, self.plan)
            require(self.api.supervisor().get("enabled") is True, "CRM_MUST_START_ENABLED")
            require(self.ready() is True, "INDEPENDENT_WATCHDOG_NOT_READY")
            self.save(journal, "ADMITTED", admission=admitted, provider_inventory=inventory,
                      backup_manifest_sha256=self.transport.backup_sha256, owned_trigger_id=getattr(self.api, "id", None))
        if recovery and journal["stage"] == "ADMITTED":
            return self.finish(journal, success=False, phase_status="NOT_STARTED", watchdog_status="RECOVERED", no_pause_or_write=True)
        try:
            if not recovery:
                self.transport.revalidate()
                self.admission.check(operation=self.operation)
                self.inventory(self.api, self.plan)
                placement = self.worker.pre_pause_namespace()
                require(placement.get("status") == "CRM_NAMESPACE_VERIFIED", "EXACT_CRM_NAMESPACE_REQUIRED")
                journal["namespace"] = placement
                self.save(journal, "PAUSE_INTENT")
                self.api.set_enabled(False)
                self.save(journal, "PAUSED")
                self.save(journal, "OPERATION_INTENT")
                def before_callback():
                    before = self.worker.verify_phase_before(self.operation)
                    self.save(journal, "OPERATION_INTENT", logical_before=before["application_data_sha256"])
                installed = self.operation == "execute"
                phase = self.worker.perform_phase(self.operation, self.transport.backup_sha256, before_callback,
                    lambda: self.evidence(self.worker, installed=installed))
                result = phase["mechanical"]
                if self.operation == "backup":
                    require(result.get("status") == "BACKUP_VERIFIED", "BACKUP_NOT_VERIFIED")
                    backup_sha = result["backup_manifest_sha256"]
                else:
                    backup_sha = self.transport.backup_sha256
                self.save(journal, "OPERATION_DONE", mechanical=result, installed=installed, backup_manifest_sha256=backup_sha,
                          paused_after=phase["after"])
            elif journal["stage"] in ("PAUSE_INTENT", "PAUSED", "OPERATION_INTENT", "RESTORE_INTENT"):
                # Recovery never initiates a fresh backup or install.
                self.api.set_enabled(False)
                outcome = self.worker.recover()
                installed = outcome == "INSTALLED"
                if self.operation in ("backup", "rollback") and installed:
                    self.worker.rollback_existing(self.transport.backup_sha256)
                    installed = False
                self.save(journal, "OPERATION_DONE", installed=installed, recovered=True,
                          phase_success=self.operation == "execute" and installed or self.operation == "rollback" and not installed)
            if journal["stage"] == "OPERATION_DONE":
                installed = journal["installed"]
                self.api.reload()
                http = self.probe(self.plan, installed=installed)
                after = journal.get("paused_after") or self.evidence(self.worker, installed=installed)
                if self.operation == "execute" and installed and "rollback_readiness" not in after:
                    with self.worker.lease() as lease:
                        after = self.evidence(self.worker, installed=True)
                        after["rollback_readiness"] = self.worker.rollback_readiness(lease, journal["backup_manifest_sha256"])
                proofs = self.proofs(journal, after, http)
                self.save(journal, "READY_RESUME", proofs=proofs)
            if journal["stage"] == "READY_RESUME":
                self.save(journal, "RESUME_INTENT", resume_epoch=time.time())
            if journal["stage"] == "RESUME_INTENT":
                resumed = self.api.set_enabled(True)
                self.save(journal, "RESUMED", crm_resume=resumed)
            if journal["stage"] == "RESUMED":
                if journal.get("restoration_unverified"):
                    return self.finish(journal, success=False, phase_status="RESTORATION_UNVERIFIED", watchdog_status="RECOVERED",
                        proofs={"crm_resume": journal["crm_resume"]}, error_code=journal["restoration_error"], recovery_confirmed=False)
                runtime = self.worker.startup(since_epoch=journal["resume_epoch"], installed=journal["installed"])
                proofs = dict(journal["proofs"], runtime=runtime, crm_resume=journal["crm_resume"])
                success = journal.get("phase_success", True)
                phase_status = {"backup": "BACKUP_VERIFIED", "execute": "COMPLETE", "rollback": "ROLLED_BACK"}[self.operation]
                return self.finish(journal, success=success, phase_status=phase_status if success else "RESTORED_AFTER_FAILURE",
                                   watchdog_status="COMPLETE" if success else "ROLLED_BACK", proofs=proofs)
            raise RuntimeError("UNKNOWN_PHASE_STAGE")
        except Exception as exc:
            if journal.get("stage") == "ADMITTED":
                return self.finish(journal, success=False, phase_status="NOT_STARTED", watchdog_status="RECOVERED",
                                   no_pause_or_write=True, error_code=safe_error_code(exc))
            if journal.get("stage") == "RESUME_INTENT":
                # The server may have enabled despite a timeout. Only its
                # exact read-back is retried by watchdog recovery.
                raise
            try:
                self.save(journal, "RESTORE_INTENT", phase_success=False, original_error=type(exc).__name__)
                self.api.set_enabled(False)
                outcome = self.worker.recover()
                installed = outcome == "INSTALLED"
                if installed and self.operation == "execute":
                    self.worker.rollback_existing(self.transport.backup_sha256)
                    installed = False
                self.api.reload()
                http = self.probe(self.plan, installed=installed)
                after = self.evidence(self.worker, installed=installed)
                # Recovery preserves the current database; it never substitutes
                # an older original snapshot for newer operator data.
                proofs = self.proofs(journal, after, http)
                self.save(journal, "RESUME_INTENT", resume_epoch=time.time(), installed=installed, proofs=proofs)
                resumed = self.api.set_enabled(True)
                self.save(journal, "RESUMED", crm_resume=resumed)
                runtime = self.worker.startup(since_epoch=journal["resume_epoch"], installed=installed)
                return self.finish(journal, success=False, phase_status="RESTORED_AFTER_FAILURE", watchdog_status="ROLLED_BACK",
                                   proofs=dict(proofs, runtime=runtime, crm_resume=resumed), error_code=type(exc).__name__)
            except Exception as restore:
                if journal.get("stage") == "RESUME_INTENT":
                    raise
                # A failed code/HTTP proof must not indefinitely disable CRM.
                # Resume is bounded by ProviderAPI; this cannot become PASS.
                self.save(journal, "RESUME_INTENT", resume_epoch=time.time(), phase_success=False,
                          restoration_unverified=True, restoration_error=type(restore).__name__, proofs={})
                resumed = self.api.set_enabled(True)
                return self.finish(journal, success=False, phase_status="RESTORATION_UNVERIFIED", watchdog_status="RECOVERED",
                                   proofs={"crm_resume": resumed}, error_code=type(restore).__name__, recovery_confirmed=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context")
    parser.add_argument("--context-sha256")
    parser.add_argument("--operation", choices=sorted(OPERATIONS))
    parser.add_argument("--recover")
    args = parser.parse_args(argv)
    if not args.context and not args.recover:
        require(args.context_sha256 is None and args.operation is None, "CONTEXT_ARGUMENTS_REQUIRED")
        print(json.dumps({"mode": "INSPECT_ONLY", "operations": sorted(OPERATIONS)}))
        return 0
    require(bool(args.context) != bool(args.recover), "ONE_CONTEXT_MODE_REQUIRED")
    recovering = bool(args.recover)
    if recovering:
        require(args.operation is None, "RECOVERY_OPERATION_FROM_BOUND_CONTEXT_ONLY")
        watcher = json.loads(bounded_read(args.recover, args.context_sha256))
        transport = TransportContext(watcher["lifecycle_plan_path"], watcher["lifecycle_plan_sha256"])
    else:
        require(args.operation in OPERATIONS, "EXACT_OPERATION_REQUIRED")
        transport = TransportContext(args.context, args.context_sha256, args.operation)
    try:
        return execute_context(transport, args, recovering, watcher if recovering else None)
    except Exception as exc:
        if not recovering and prepause_refusal(transport, safe_error_code(exc)):
            return 1
        raise


def execute_context(transport, args, recovering, watcher):
    # All local executable sources have been verified before any import.
    if str(transport.root) not in sys.path:
        sys.path.insert(0, str(transport.root))
    if not recovering:
        previous = terminal_reentry(transport)
        if previous is not None:
            return 0 if previous["status"] == "PASS" else 1
    from package_install import Package, atomic
    from lifecycle_controller import ProviderAPI, RepositoryAdmission, verify_installation_policy
    from lifecycle_worker import InstallWorker
    from watchdog import BoundContext, LinuxProcesses, launch_watchdog
    verify_installation_policy(transport.plan)
    normalize_credential(recovery=recovering)
    raw_api = ProviderAPI()
    previous_journal = (json.loads(bounded_read(transport.root / "phase-journal.json"))
                        if recovering and (transport.root / "phase-journal.json").exists() else {})
    api = OwnedTriggerAPI(raw_api, transport, recovery=recovering, expected_id=previous_journal.get("owned_trigger_id"))
    package = Package(transport.manifest_path.parent, transport.plan["package_manifest_sha256"])
    require(not package.report()["runtime_payload_missing"] and not package.report()["writer_payload_missing"], "COMPLETE_RELEASE_REQUIRED")
    if recovering:
        bound = BoundContext(args.recover, args.context_sha256, watcher["watchdog_source_sha256"])
        require(bound.data["recovery_argv"][3] == str(transport.root / "remote_worker.py"), "RECOVERY_ENTRYPOINT_BINDING")
        watchdog_path, watchdog_sha = Path(args.recover), args.context_sha256
        plan = copy.deepcopy(transport.plan)
        plan["authority"]["repository_root"] = str(transport.root / "authority")
        plan["authority"]["source_repository_root"] = str(transport.root / (
            "source_authority" if transport.operation == "rollback" else "authority"))
    else:
        plan = checkout_authority(transport)
        RepositoryAdmission(plan).check(operation=transport.operation)
        try:
            os.setsid()
        except PermissionError:
            pass
        require(os.getpid() == os.getpgrp() == os.getsid(0), "DEDICATED_PHASE_SESSION_REQUIRED")
        watchdog_path = transport.root / "watchdog-context.json"
        require(not watchdog_path.exists() and not watchdog_path.is_symlink(), "FRESH_PHASE_OWNER_REQUIRED")
        ticks = LinuxProcesses().identity(os.getpid())["start_ticks"]
        watcher = {"owner_pid": os.getpid(), "pgid": os.getpgrp(), "start_ticks": ticks,
                   "deadline_epoch": time.time() + plan["maximum_seconds"],
                   "result_path": str(transport.root / "watchdog-terminal.json"),
                   "recovery_argv": [sys.executable, "-I", "-B", str(transport.root / "remote_worker.py"), "--recover",
                                     str(watchdog_path), "--context-sha256", "@CONTEXT_SHA256@"],
                   "recovery_source_sha256": plan["package_sources"]["remote_worker.py"],
                   "watchdog_source_sha256": plan["package_sources"]["watchdog.py"],
                   "package_manifest_path": str(transport.manifest_path), "package_manifest_sha256": package.manifest_sha,
                   "lifecycle_plan_path": str(transport.path), "lifecycle_plan_sha256": transport.sha256,
                   "credential_env_names": ["PYTHONANYWHERE_API_TOKEN"]}
        raw = encoded(watcher)
        atomic(watchdog_path, raw)
        watchdog_sha = sha(raw)
        launch_watchdog(watchdog_path, watchdog_sha, watcher["watchdog_source_sha256"], watcher["recovery_argv"][:-1] + [watchdog_sha])
    command = [Path(sys.executable).name, "-I", "-B", str(transport.root / "watchdog.py"), "--watch", str(watchdog_path),
               "--context-sha256", watchdog_sha, "--watchdog-sha256", watcher["watchdog_source_sha256"]]
    worker = InstallWorker(package, transaction_id=transport.value["transaction_id"],
                           allowed_python_sha256=[plan["provider"]["monitor_python_sha256"], sha(encoded(command)), sha(encoded(api.argv))])
    runner = PhaseRunner(transport=transport, watchdog_context=watcher, watchdog_sha256=watchdog_sha, plan=plan,
                         admission=RepositoryAdmission(plan), api=api, worker=worker, watchdog_ready=lambda: True)
    result = runner.run(recovery=recovering)
    # The transport reads durable files; stdout contains no credentials/output
    # traces and never substitutes for the bound completion marker.
    print(json.dumps({"operation": transport.operation, "status": result["status"], "phase_status": result["phase_status"]}))
    return 0 if result["status"] == "PASS" or recovering and result["safe_to_stop"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error_code": type(exc).__name__}))
        raise SystemExit(1)
