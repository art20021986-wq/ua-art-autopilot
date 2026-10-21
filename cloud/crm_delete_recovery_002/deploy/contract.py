"""Read-only identity and evidence contract for the installation child task.

This module neither grants authority nor turns fixture results into production
evidence. The caller must obtain results through its verified transport. A final
receipt finishes only installation; the parent still needs live Telegram
acceptance. No receipt is written here, and an existing target always refuses.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping


PARENT_TASK_ID = "UA-ART-CRM-DELETE-RECOVERY-002"
TASK_ID = PARENT_TASK_ID + "-INSTALL"
PACKAGE_REL = "cloud/crm_delete_recovery_002/deploy"
REQUEST_REL = "tasks/requests/" + TASK_ID + ".json"
MANIFEST_REL = "tasks/manifests/" + TASK_ID + ".json"
APPROVAL_REL = "tasks/approvals/" + TASK_ID + ".production.json"
GATE_A_REL = "tasks/gates/" + TASK_ID + ".json"
RECEIPT_REL = "state/receipts/" + TASK_ID + ".json"
BACKUP_RECEIPT_REL = "state/receipts/" + TASK_ID + "-BACKUP.json"
ROLLBACK_RECEIPT_REL = "state/receipts/" + TASK_ID + "-ROLLBACK.json"
CRITICAL_CONTRACT = "UA-ART-CRITICAL-ADAPTER-V1.0"
REMOTE_RESULT_SCHEMA = "ua-art-crm-delete-recovery-002-remote-receipt-v1"
RECEIPT_SCOPE = "INSTALLATION_AND_RUNTIME_HTTP_VERIFY"
PARENT_PENDING = "PENDING_LIVE_TELEGRAM_ACCEPTANCE"
BACKUP_RECEIPT_SCHEMA = "UA-ART-PRODUCTION-BACKUP-RECEIPT-1"
ROLLBACK_RECEIPT_SCHEMA = "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1"
BINDING_KEYS = {"task_id", "request_sha256", "run_id", "transaction_id",
                "manifest_sha256", "backup_manifest_sha256"}
BACKUP_RECEIPT_KEYS = BINDING_KEYS | {
    "schema_version", "operation", "status", "backup", "unexpected_changes"}
ROLLBACK_RECEIPT_KEYS = BINDING_KEYS | {
    "schema_version", "operation", "status", "rollback", "restored",
    "unexpected_changes", "protected_files_unchanged", "crm_unchanged", "live_verify"}
SHA = re.compile(r"[0-9a-f]{64}")
RUNTIME_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
OWNER_APPROVAL_KEYS = {"approved_at", "authorization_id", "authorized_environment", "expires_at",
    "gate_a_sha256", "launch_nonce", "manifest_sha256", "mode_epoch", "owner", "owner_authorized",
    "production_allowed", "request_path", "request_subject_sha256", "schema_version", "task_id"}
DELETION_TABLES = {"ua_delete_confirmations", "ua_delete_intents", "ua_delete_jobs"}
SCHEMA_OPERATION_PATH = "production/crm.db"


class ContractError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ContractError(reason)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def request_authorization_sha256(request: Mapping[str, Any]) -> str:
    """Use the existing autostart subject binding, without an approval hash cycle."""
    critical = dict(_object(request.get("critical"), "critical"))
    require("owner_approval_sha256" in critical, "OWNER_APPROVAL_SUBJECT_REQUIRED")
    critical["owner_approval_sha256"] = "0" * 64
    return sha(canonical_json(dict(request, critical=critical)))


def require_sha(value: Any, name: str) -> str:
    require(isinstance(value, str) and SHA.fullmatch(value) is not None,
            "SHA256_INVALID:" + name)
    return value


def _object(value: Any, name: str) -> dict[str, Any]:
    require(isinstance(value, dict), "OBJECT_REQUIRED:" + name)
    return value


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _invalid_number(value: str) -> None:
    raise ContractError("JSON_NONFINITE_NUMBER")


def decode_object(raw: bytes, name: str) -> dict[str, Any]:
    try:
        return _object(json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates,
                                  parse_constant=_invalid_number), name)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("JSON_INVALID:" + name) from exc


def repo_path(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and re.fullmatch(r"[A-Za-z0-9._/-]+", relative) is not None,
            "REPO_PATH_INVALID")
    pure = PurePosixPath(relative)
    require(not pure.is_absolute() and bool(pure.parts) and ".." not in pure.parts
            and pure.as_posix() == relative, "REPO_PATH_SCOPE")
    current = root
    for part in pure.parts:
        current = current / part
        require(not current.is_symlink(), "REPO_PATH_SYMLINK")
    require(current.resolve(strict=False).is_relative_to(root), "REPO_PATH_ESCAPE")
    return current


def read_file(root: Path, relative: str) -> bytes:
    path = repo_path(root, relative)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ContractError("BOUND_FILE_UNAVAILABLE:" + relative) from exc
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= 16 * 1024 * 1024,
                "BOUND_FILE_INVALID:" + relative)
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(16 * 1024 * 1024 + 1)
        after = os.fstat(descriptor)
        require(len(raw) <= 16 * 1024 * 1024 and (info.st_ino, info.st_size, info.st_mtime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns), "BOUND_FILE_CHANGED:" + relative)
        return raw
    finally:
        os.close(descriptor)


def _required_env(environment: Mapping[str, str], key: str) -> str:
    value = environment.get(key)
    require(isinstance(value, str) and 0 < len(value) <= 256 and
            not any(character in value for character in "\r\n\0"), "ENV_INVALID:" + key)
    return value


def _inspect_python(raw: bytes, name: str) -> None:
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=name)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise ContractError("PYTHON_INVALID:" + name) from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            require(all(item.name.split(".")[0] not in {"pty", "telnetlib"}
                        for item in node.names), "PYTHON_DENIED_IMPORT:" + name)
        if isinstance(node, ast.ImportFrom):
            require((node.module or "").split(".")[0] not in {"pty", "telnetlib"},
                    "PYTHON_DENIED_IMPORT:" + name)
        if not isinstance(node, ast.Call):
            continue
        require(not (isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval"}),
                "PYTHON_DENIED_CALL:" + name)
        require(not (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                     and node.func.value.id == "os" and node.func.attr in {"system", "popen"}),
                "PYTHON_DENIED_OS_EXECUTION:" + name)
        require(not any(item.arg == "shell" and isinstance(item.value, ast.Constant)
                        and item.value.value is True for item in node.keywords),
                "PYTHON_SHELL_TRUE:" + name)


def _execution_files(root: Path, execution: Mapping[str, Any]) -> dict[str, str]:
    files: dict[str, str] = {}
    for prefix, filename in (("", "controller.py"), ("backup_", "backup_controller.py"),
                             ("rollback_", "rollback_controller.py")):
        relative = PACKAGE_REL + "/" + filename
        require(execution.get(prefix + "controller_path") == relative,
                "CONTROLLER_PATH_IDENTITY:" + prefix)
        files[relative] = require_sha(execution.get(prefix + "controller_sha256"), prefix + "controller")
    tests, dependencies = execution.get("test_paths"), execution.get("dependency_paths")
    require(isinstance(tests, list) and 0 < len(tests) <= 20 and
            all(isinstance(item, str) for item in tests), "TEST_PATHS_INVALID")
    require(isinstance(dependencies, list) and len(dependencies) <= 50 and
            all(isinstance(item, str) for item in dependencies), "DEPENDENCY_PATHS_INVALID")
    require(len(set(tests)) == len(tests) and len(set(dependencies)) == len(dependencies),
            "EXECUTION_PATH_DUPLICATE")
    declared = _object(execution.get("file_sha256"), "file_sha256")
    require(set(declared) == set(tests) | set(dependencies), "FILE_HASH_KEY_SET")
    require(not (set(files) & set(declared)), "CONTROLLER_DEPENDENCY_COLLISION")
    for name, digest in declared.items():
        require(name.startswith(PACKAGE_REL + "/") and name.endswith(".py"), "DEPENDENCY_SCOPE")
        files[name] = require_sha(digest, name)
    for name, digest in files.items():
        raw = read_file(root, name)
        require(sha(raw) == digest, "EXECUTABLE_HASH_MISMATCH:" + name)
        _inspect_python(raw, name)
    package = repo_path(root, PACKAGE_REL)
    inventory: set[str] = set()
    for current, directories, names in os.walk(package, followlinks=False):
        for name in directories:
            entry = Path(current) / name
            require(not entry.is_symlink() and name != "__pycache__", "PACKAGE_IMPORT_DIRECTORY")
        for name in names:
            entry = Path(current) / name
            require(not entry.is_symlink() and entry.suffix.lower() not in
                    {".pyc", ".pyo", ".so", ".pyd", ".dll", ".dylib"}, "PACKAGE_IMPORT_ARTIFACT")
            if entry.suffix == ".py":
                inventory.add(entry.relative_to(root).as_posix())
    require(inventory == set(files), "PACKAGE_PYTHON_CLOSURE")
    digest = sha(canonical_json(dict(sorted(files.items()))))
    if "dependency_sha256" in execution:
        require(execution["dependency_sha256"] == digest, "DEPENDENCY_DIGEST_MISMATCH")
    return files


@dataclass(frozen=True)
class Envelope:
    root: Path
    operation: str
    values: Mapping[str, str]
    request: Mapping[str, Any]
    manifest: Mapping[str, Any]
    owner_approval: Mapping[str, Any]
    gate_a: Mapping[str, Any]
    file_sha256: Mapping[str, str]
    dependency_sha256: str
    receipt_path: Path
    package_manifest_sha256: str
    installation_policy_sha256: str

    @property
    def task_id(self) -> str:
        return TASK_ID

    @property
    def request_sha256(self) -> str:
        return self.values["UAART_REQUEST_SHA256"]

    @property
    def manifest_sha256(self) -> str:
        return self.values["UAART_MANIFEST_SHA256"]

    @property
    def run_id(self) -> str:
        return self.values["UAART_RUN_ID"]

    @property
    def transaction_id(self) -> str:
        return self.values["UAART_TRANSACTION_ID"]

    @property
    def backup_manifest_sha256(self) -> str | None:
        return self.values.get("UAART_BACKUP_MANIFEST_SHA256")

    @property
    def release_manifest_sha256(self) -> str:
        return self.package_manifest_sha256

    @property
    def static_policy_sha256(self) -> str:
        return self.installation_policy_sha256

    @property
    def bindings(self) -> dict[str, str]:
        value = {"task_id": TASK_ID, "request_sha256": self.request_sha256,
                 "run_id": self.run_id, "transaction_id": self.transaction_id,
                 "manifest_sha256": self.manifest_sha256}
        if self.backup_manifest_sha256 is not None:
            value["backup_manifest_sha256"] = self.backup_manifest_sha256
        return value


def _validate_manifest(request: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    require(manifest.get("task_id") == TASK_ID and manifest.get("task_class") == "CRITICAL"
            and manifest.get("contract_id") == CRITICAL_CONTRACT
            and manifest.get("production_write") is True, "MANIFEST_SCOPE")
    for key in ("backup_required", "rollback_required", "live_verify_required"):
        require(manifest.get(key) is True, "MANIFEST_REQUIRED:" + key)
    operations = manifest.get("operations")
    require(isinstance(operations, list) and bool(operations), "MANIFEST_OPERATIONS")
    paths = []
    for operation in operations:
        item = _object(operation, "operation")
        path = item.get("path")
        require(isinstance(path, str) and re.fullmatch(r"[A-Za-z0-9._/-]+", path) is not None
                and path == PurePosixPath(path).as_posix() and not path.startswith("/")
                and ".." not in PurePosixPath(path).parts, "MANIFEST_OPERATION_PATH")
        require(item.get("action") in {"create", "replace", "delete", "noop"}, "MANIFEST_ACTION")
        if item.get("expected_before_sha256") is not None:
            require_sha(item["expected_before_sha256"], "operation_before")
        if item["action"] in {"create", "replace"}:
            require_sha(item.get("expected_after_sha256"), "operation_after")
        paths.append(path)
    changed = request.get("changed_paths")
    require(isinstance(changed, list) and all(isinstance(item, str) for item in changed)
            and len(set(paths)) == len(paths) and set(changed) == set(paths), "MANIFEST_CHANGED_PATHS")
    schema_operations = [item for item in operations if item["path"] == SCHEMA_OPERATION_PATH]
    require(len(schema_operations) == 1 and schema_operations[0].get("digest_scope") == "sqlite_schema"
            and schema_operations[0].get("action") == "replace"
            and schema_operations[0].get("database_file_hash_claimed") is False
            and schema_operations[0].get("fresh_projection_verification_required") is True,
            "EXACT_SQLITE_SCHEMA_OPERATION_REQUIRED")
    require_sha(schema_operations[0].get("expected_before_sha256"), "schema_projection_before")
    for prefix in ("before", "after"):
        projection = _object(schema_operations[0].get(prefix + "_projection"), prefix + "_schema_projection")
        require(set(projection) == DELETION_TABLES and
                sha(canonical_json(projection)) == schema_operations[0].get("expected_" + prefix + "_sha256"),
                "SCHEMA_OPERATION_PROJECTION_BINDING")
    require_sha(schema_operations[0].get("migration_payload_sha256"), "schema_migration_payload")
    protected = manifest.get("protected_paths")
    require(isinstance(protected, list) and bool(protected) and
            all(isinstance(item, str) for item in protected) and
            not set(protected) & set(paths), "MANIFEST_PROTECTED_SCOPE")


def _backup_receipt(envelope: Envelope) -> dict[str, Any]:
    value = decode_object(read_file(envelope.root, BACKUP_RECEIPT_REL), "backup_receipt")
    require(set(value) == BACKUP_RECEIPT_KEYS and value.get("schema_version") == BACKUP_RECEIPT_SCHEMA
            and value.get("operation") == "backup" and value.get("status") == "PASS"
            and value.get("backup") == "PASS", "BACKUP_RECEIPT_SCHEMA")
    require(type(value.get("unexpected_changes")) is int and value["unexpected_changes"] == 0,
            "BACKUP_RECEIPT_UNEXPECTED_CHANGES")
    for key, expected in _bindings(envelope).items():
        require(value.get(key) == expected and isinstance(value.get(key), str), "BACKUP_RECEIPT_BINDING:" + key)
    return value


def load_envelope(root: Path, environment: Mapping[str, str], operation: str) -> Envelope:
    """Reject any mutable identity mismatch before the caller contacts production.

    A real control-plane launch/admission check is still mandatory. This function
    validates existing documents and never creates approvals, requests or files.
    """
    root = Path(root)
    require(root.is_absolute() and root.is_dir() and root.resolve(strict=True) == root,
            "CANONICAL_REPOSITORY_ROOT_REQUIRED")
    require(operation in {"backup", "execute", "rollback"}, "OPERATION_INVALID")
    names = ("UAART_OPERATION", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256", "UAART_TASK_ID",
             "UAART_TASK_CLASS", "UAART_RUN_ID", "UAART_TRANSACTION_ID", "UAART_MANIFEST_SHA256",
             "UAART_RECEIPT_PATH")
    values = {name: _required_env(environment, name) for name in names}
    require(values["UAART_OPERATION"] == operation, "OPERATION_IDENTITY")
    require(values["UAART_TASK_ID"] == TASK_ID and values["UAART_TASK_CLASS"] == "CRITICAL", "TASK_IDENTITY")
    require(values["UAART_REQUEST_PATH"] == REQUEST_REL, "REQUEST_PATH_IDENTITY")
    for key in ("UAART_RUN_ID", "UAART_TRANSACTION_ID"):
        require(RUNTIME_ID.fullmatch(values[key]) is not None, "RUNTIME_IDENTITY:" + key)
    for key in ("UAART_REQUEST_SHA256", "UAART_MANIFEST_SHA256"):
        require_sha(values[key], key)
    receipts = {"backup": BACKUP_RECEIPT_REL, "execute": RECEIPT_REL, "rollback": ROLLBACK_RECEIPT_REL}
    require(values["UAART_RECEIPT_PATH"] == receipts[operation], "RECEIPT_IDENTITY")
    if operation != "execute":
        alias = "UAART_" + operation.upper() + "_RECEIPT_PATH"
        values[alias] = _required_env(environment, alias)
        require(values[alias] == receipts[operation], "RECEIPT_ALIAS_IDENTITY")
    target = repo_path(root, receipts[operation])
    require(not target.exists(), "RECEIPT_PREEXISTING")
    raw_request = read_file(root, REQUEST_REL)
    require(sha(raw_request) == values["UAART_REQUEST_SHA256"], "REQUEST_HASH_MISMATCH")
    request = decode_object(raw_request, "request")
    require(request.get("task_id") == TASK_ID and request.get("parent_task_id") == PARENT_TASK_ID
            and request.get("production_required") is True and request.get("requested_min_class") == "CRITICAL"
            and request.get("acceptance_scope") == RECEIPT_SCOPE, "REQUEST_SCOPE")
    critical = _object(request.get("critical"), "critical")
    execution = _object(request.get("execution"), "execution")
    require(critical.get("manifest_path") == MANIFEST_REL and critical.get("owner_approval_path") == APPROVAL_REL,
            "AUTHORITY_PATH_IDENTITY")
    manifest = decode_object(read_file(root, MANIFEST_REL), "manifest")
    manifest_sha = sha(canonical_json(manifest))
    require(critical.get("manifest_sha256") == manifest_sha == values["UAART_MANIFEST_SHA256"],
            "MANIFEST_HASH_MISMATCH")
    _validate_manifest(request, manifest)
    approval_bytes = read_file(root, APPROVAL_REL)
    require(sha(approval_bytes) == require_sha(critical.get("owner_approval_sha256"), "owner_approval"),
            "OWNER_APPROVAL_HASH_MISMATCH")
    approval = decode_object(approval_bytes, "owner_approval")
    require(set(approval) == OWNER_APPROVAL_KEYS
            and approval.get("schema_version") == "UA-ART-PRODUCTION-AUTHORIZATION-1"
            and approval.get("task_id") == TASK_ID and approval.get("manifest_sha256") == manifest_sha
            and approval.get("authorized_environment") == "production"
            and approval.get("owner_authorized") is True and approval.get("production_allowed") is True
            and approval.get("request_path") == REQUEST_REL and critical.get("gate_b_authorized") is True,
            "STRUCTURED_INSTALLATION_AUTHORITY_REQUIRED")
    require(approval.get("request_subject_sha256") == request_authorization_sha256(request),
            "OWNER_APPROVAL_REQUEST_SUBJECT_BINDING")
    package_sha = require_sha(request.get("package_manifest_sha256"), "package_manifest")
    policy_sha = require_sha(request.get("installation_policy_sha256"), "installation_policy")
    for document in (manifest,):
        require(document.get("package_manifest_sha256") == package_sha and
                document.get("installation_policy_sha256") == policy_sha and
                document.get("acceptance_scope") == RECEIPT_SCOPE and
                document.get("parent_task_id") == PARENT_TASK_ID, "INSTALLATION_POLICY_BINDING")
    for prefix, expected in (("", RECEIPT_REL), ("backup_", BACKUP_RECEIPT_REL),
                             ("rollback_", ROLLBACK_RECEIPT_REL)):
        require(execution.get(prefix + "receipt_path") == expected, "EXECUTION_RECEIPT_IDENTITY")
    require(execution.get("production_required") is True, "EXECUTION_PRODUCTION_REQUIRED")
    evidence = execution.get("evidence_paths")
    require(isinstance(evidence, list) and set(receipts.values()).issubset(evidence), "RECEIPT_EVIDENCE_REQUIRED")
    files = _execution_files(root, execution)
    dependency_sha = sha(canonical_json(dict(sorted(files.items()))))
    require(critical.get("gate_a_path") == GATE_A_REL, "GATE_A_PATH_IDENTITY")
    gate_raw = read_file(root, GATE_A_REL)
    gate_sha = sha(gate_raw)
    require(gate_sha == require_sha(critical.get("gate_a_sha256"), "gate_a")
            and approval.get("gate_a_sha256") == gate_sha, "GATE_A_HASH_BINDING")
    gate = decode_object(gate_raw, "gate_a")
    require(gate.get("contract_id") == CRITICAL_CONTRACT and gate.get("task_id") == TASK_ID
            and gate.get("status") == "PASS" and gate.get("production_write") is False
            and gate.get("tests") == "PASS" and type(gate.get("unexpected_changes")) is int
            and gate["unexpected_changes"] == 0 and gate.get("backup_plan_ready") is True
            and gate.get("rollback_plan_ready") is True and gate.get("manifest_sha256") == manifest_sha,
            "GATE_A_NOT_PROVEN")
    _hash_map(gate.get("protected_snapshot"), "gate_a_protected")
    tests = _object(gate.get("test_evidence"), "gate_a_test_evidence")
    require(type(tests.get("passed")) is int and tests["passed"] > 0
            and type(tests.get("failed")) is int and tests["failed"] == 0
            and type(tests.get("skipped")) is int and tests["skipped"] == 0
            and tests.get("dependency_sha256") == dependency_sha, "GATE_A_TEST_CLOSURE_NOT_PROVEN")
    if operation in {"execute", "rollback"}:
        values["UAART_BACKUP_MANIFEST_SHA256"] = require_sha(
            _required_env(environment, "UAART_BACKUP_MANIFEST_SHA256"), "backup_manifest")
    elif environment.get("UAART_BACKUP_MANIFEST_SHA256"):
        raise ContractError("BACKUP_OPERATION_HAS_STALE_BACKUP_BINDING")
    envelope = Envelope(root, operation, values, request, manifest, approval, gate, files,
                        dependency_sha, target, package_sha, policy_sha)
    if operation in {"execute", "rollback"}:
        _backup_receipt(envelope)
    return envelope


def _bindings(envelope: Envelope, backup_sha: str | None = None) -> dict[str, str]:
    return {"task_id": TASK_ID, "request_sha256": envelope.request_sha256,
            "run_id": envelope.run_id, "transaction_id": envelope.transaction_id,
            "manifest_sha256": envelope.manifest_sha256,
            "backup_manifest_sha256": require_sha(backup_sha or envelope.backup_manifest_sha256, "backup_manifest")}


def _package_json(value: Any) -> bytes:
    """The existing installer backup format; distinct from CRITICAL canonical JSON."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _hash_map(value: Any, label: str, *, allow_absent: bool = False) -> dict[str, str | None]:
    result = _object(value, label)
    require(bool(result), "HASH_MAP_EMPTY:" + label)
    for key, digest in result.items():
        require(isinstance(key, str) and bool(key), "HASH_MAP_PATH:" + label)
        if digest is None and allow_absent:
            continue
        require_sha(digest, label + ":" + key)
    return result


def _release_proof(envelope: Envelope, proofs: Mapping[str, Any]) -> dict[str, Any]:
    text = proofs.get("package_manifest_text")
    require(isinstance(text, str) and len(text) <= 1024 * 1024, "PACKAGE_MANIFEST_PROOF_REQUIRED")
    raw = text.encode("utf-8")
    require(sha(raw) == envelope.package_manifest_sha256, "PACKAGE_MANIFEST_PROOF_HASH")
    release = decode_object(raw, "release_manifest")
    require(release.get("format") == 1 and release.get("task") == PARENT_TASK_ID + "-v1.0"
            and release.get("root") == "/home/Carix"
            and release.get("supervisor") == {"id": 266084, "command": "python3.10 /home/Carix/start_safe.py"},
            "PACKAGE_MANIFEST_PROOF_SCOPE")
    require_sha(release.get("application_schema_sha256"), "application_schema")
    files = release.get("files")
    require(isinstance(files, list) and bool(files), "PACKAGE_MANIFEST_FILES")
    destinations = []
    for file in files:
        item = _object(file, "release_file")
        destination = item.get("destination")
        require(isinstance(destination, str) and destination.endswith(".py") and
                PurePosixPath(destination).as_posix() == destination and not destination.startswith("/")
                and ".." not in PurePosixPath(destination).parts, "PACKAGE_FILE_SCOPE")
        require_sha(item.get("payload_sha256"), "payload")
        if item.get("before_sha256") is not None:
            require_sha(item["before_sha256"], "before")
        destinations.append(destination)
    require(len(set(destinations)) == len(destinations) and "cars_ui.py" in destinations, "PACKAGE_FILE_SET")
    guards = _hash_map(release.get("source_guards"), "release_guards")
    require({"db.py", "run_all.py", "start_safe.py", "publication_fence.py"} <= set(guards),
            "PACKAGE_REQUIRED_GUARDS")
    route = _object(release.get("route_patch"), "release_route")
    require(route.get("destination") == "/var/www/www_uaart_com_ua_wsgi.py", "PACKAGE_ROUTE_SCOPE")
    require_sha(route.get("before_sha256"), "wsgi_before")
    require_sha(route.get("payload_sha256"), "wsgi_after")
    config = _object(release.get("runtime_config"), "release_config")
    require(config.get("destination") == "ua_crm_deletion_state/runtime.json", "PACKAGE_CONFIG_SCOPE")
    require_sha(config.get("payload_sha256"), "runtime_config")
    schema = _object(release.get("deletion_schema"), "release_deletion_schema")
    require_sha(schema.get("sha256"), "deletion_schema_source")
    return release


def _verify_schema_proof(envelope: Envelope, proofs: Mapping[str, Any],
                          release: Mapping[str, Any]) -> str:
    """Bind only the three additive DDL objects; never pretend this is a DB file hash."""
    text = proofs.get("schema_source_text")
    require(isinstance(text, str) and len(text) <= 1024 * 1024, "SCHEMA_SOURCE_PROOF_REQUIRED")
    require(sha(text.encode("utf-8")) == release["deletion_schema"]["sha256"], "SCHEMA_SOURCE_PROOF_HASH")
    try:
        tree = ast.parse(text, filename="pinned_deletion_schema.py")
        assignments = [node for node in tree.body if isinstance(node, ast.Assign) and
                       any(isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets)]
        require(len(assignments) == 1, "EXACT_SCHEMA_ASSIGNMENT_REQUIRED")
        schema = ast.literal_eval(assignments[0].value)
    except (SyntaxError, ValueError, TypeError, RecursionError) as exc:
        raise ContractError("SCHEMA_LITERAL_INVALID") from exc
    require(isinstance(schema, dict) and set(schema) == DELETION_TABLES and
            all(isinstance(ddl, str) and ddl.startswith("CREATE TABLE " + name + " (")
                for name, ddl in schema.items()), "SCHEMA_SOURCE_SCOPE")
    absent = dict.fromkeys(sorted(DELETION_TABLES))
    present_sha, absent_sha = sha(canonical_json(schema)), sha(canonical_json(absent))
    operations = [item for item in envelope.manifest["operations"] if item["path"] == SCHEMA_OPERATION_PATH]
    require(len(operations) == 1, "SCHEMA_OPERATION_REQUIRED")
    operation = operations[0]
    require(operation.get("digest_scope") == "sqlite_schema" and operation.get("expected_after_sha256") == present_sha
            and operation.get("expected_before_sha256") in {absent_sha, present_sha}, "SCHEMA_MANIFEST_SOURCE_BINDING")
    require(operation.get("after_projection") == schema and operation.get("before_projection") in (absent, schema)
            and operation.get("migration_payload_sha256") == release["deletion_schema"]["sha256"],
            "SCHEMA_MANIFEST_PAYLOAD_PROJECTION_BINDING")
    preservation = _object(proofs.get("preservation"), "preservation")
    projection = _object(preservation.get("deletion_schema_projection"), "deletion_schema_projection")
    require(projection == absent or projection == schema, "DELETION_SCHEMA_PARTIAL_OR_FOREIGN")
    actual_sha = sha(canonical_json(projection))
    require(preservation.get("deletion_schema_sha256") == actual_sha, "DELETION_SCHEMA_PROJECTION_DIGEST")
    if envelope.operation == "execute":
        require(actual_sha == operation["expected_after_sha256"], "INSTALLED_DELETION_SCHEMA_NOT_PROVEN")
    elif envelope.operation == "backup":
        require(actual_sha == operation["expected_before_sha256"], "BACKUP_DELETION_SCHEMA_CHANGED")
    else:
        # Code rollback keeps an already committed additive schema. Removing it
        # or restoring the entire database would lose durable deletion intents.
        require(actual_sha in {operation["expected_before_sha256"], operation["expected_after_sha256"]},
                "ROLLBACK_DELETION_SCHEMA_NOT_PRESERVED")
    return actual_sha


def _verify_backup_proof(envelope: Envelope, proofs: Mapping[str, Any], backup_sha: str,
                         release: Mapping[str, Any]) -> None:
    proof = _object(proofs.get("backup"), "backup_proof")
    manifest = _object(proof.get("manifest"), "backup_manifest")
    code = _object(proof.get("code_manifest"), "code_backup_manifest")
    code_sha = sha(_package_json(code))
    require(sha(_package_json(manifest)) == backup_sha == proof.get("manifest_sha256"),
            "BACKUP_MANIFEST_PROOF_HASH")
    require(code_sha == proof.get("code_manifest_sha256") == manifest.get("code_backup_manifest_sha256"),
            "CODE_BACKUP_MANIFEST_PROOF_HASH")
    require(manifest.get("format") == 1 and manifest.get("package_manifest_sha256") == envelope.package_manifest_sha256
            and manifest.get("transaction_id") == envelope.transaction_id
            and manifest.get("wsgi_destination") == release["route_patch"]["destination"]
            and manifest.get("wsgi_before_sha256") == release["route_patch"]["before_sha256"]
            and type(manifest.get("wsgi_backup_mode")) is int and 0 <= manifest["wsgi_backup_mode"] <= 0o777,
            "BACKUP_MANIFEST_PROOF_BINDING")
    require(code.get("package_sha256") == envelope.package_manifest_sha256 and code.get("database_integrity") == "ok",
            "CODE_BACKUP_PROOF_BINDING")
    require_sha(code.get("database_sha256"), "database_snapshot")
    require_sha(code.get("database_logical_sha256"), "database_logical")
    file_manifest = _object(code.get("files"), "backup_files")
    expected = {item["destination"]: item.get("before_sha256") for item in release["files"]}
    expected.update(release["source_guards"])
    expected[release["runtime_config"]["destination"]] = release["runtime_config"].get("before_sha256")
    require(set(file_manifest) == set(expected), "BACKUP_FILE_SET")
    for name, digest in expected.items():
        item = _object(file_manifest[name], "backup_file")
        require(item.get("sha256") == digest, "BACKUP_FILE_PREIMAGE:" + name)
        if digest is not None:
            require_sha(digest, "backup_file")
            require(isinstance(item.get("stored"), str) and bool(item["stored"]), "BACKUP_FILE_STORAGE")
    database = _object(proof.get("database"), "backup_database")
    require(database.get("snapshot_sha256") == code["database_sha256"]
            and database.get("logical_sha256") == code["database_logical_sha256"]
            and database.get("integrity") == "ok" and database.get("wal_coherent") is True
            and proof.get("durable") is True and proof.get("files_verified") is True,
            "BACKUP_READBACK_NOT_PROVEN")


def _verify_files_and_preservation(envelope: Envelope, proofs: Mapping[str, Any],
                                   release: Mapping[str, Any]) -> None:
    installed = envelope.operation == "execute"
    field = "payload_sha256" if installed else "before_sha256"
    expected = {item["destination"]: item.get(field) for item in release["files"]}
    expected[release["route_patch"]["destination"]] = release["route_patch"][field]
    if installed:
        expected[release["runtime_config"]["destination"]] = release["runtime_config"]["payload_sha256"]
    files = _object(proofs.get("files"), "files_proof")
    require(_hash_map(files.get("expected_sha256"), "expected_files", allow_absent=True) == expected
            and _hash_map(files.get("observed_sha256"), "observed_files", allow_absent=True) == expected,
            "EXACT_CODE_READBACK_REQUIRED")
    guards = release["source_guards"]
    require(_hash_map(files.get("guarded_expected_sha256"), "expected_guards") == guards
            and _hash_map(files.get("guarded_observed_sha256"), "observed_guards") == guards,
            "EXACT_PROTECTED_READBACK_REQUIRED")
    preservation = _object(proofs.get("preservation"), "preservation")
    before = require_sha(preservation.get("crm_logical_before"), "crm_before")
    require(preservation.get("crm_logical_after") == before and
            type(preservation.get("public_or_media_writes")) is int and preservation["public_or_media_writes"] == 0
            and preservation.get("database_restored") is False and preservation.get("code_only") is True,
            "PRESERVATION_NOT_PROVEN")
    require(preservation.get("application_schema_sha256") == release["application_schema_sha256"]
            and preservation.get("database_integrity") == "ok", "APPLICATION_SCHEMA_NOT_PROVEN")
    if envelope.operation in {"backup", "execute"}:
        require(before == proofs["backup"]["code_manifest"]["database_logical_sha256"],
                "ORIGINAL_BACKUP_CRM_CHANGED")


def _verify_live_proof(envelope: Envelope, proofs: Mapping[str, Any], release: Mapping[str, Any]) -> None:
    runtime = _object(proofs.get("runtime"), "runtime")
    expected_status = "RUNTIME_RUNNING" if envelope.operation == "execute" else "BASELINE_PROCESS_RUNNING"
    require(runtime.get("status") == expected_status and type(runtime.get("pid")) is int and runtime["pid"] > 1
            and isinstance(runtime.get("start_ticks"), (str, int)) and not isinstance(runtime.get("start_ticks"), bool)
            and str(runtime["start_ticks"]).isdigit() and int(runtime["start_ticks"]) > 0
            and runtime.get("live_telegram_action_verified") is False, "RUNTIME_READBACK_REQUIRED")
    if envelope.operation == "execute":
        require(runtime.get("config_sha256") == release["runtime_config"]["payload_sha256"], "RUNTIME_CONFIG_BINDING")
    resumed = _object(proofs.get("crm_resume"), "crm_resume")
    require(resumed.get("id") == 266084 and type(resumed.get("id")) is int
            and resumed.get("enabled") is True and resumed.get("state") == "Running",
            "CRM_RESUME_NOT_PROVEN")
    checks = envelope.request.get("http_checks")
    require(isinstance(checks, dict), "REQUEST_HTTP_CHECKS_REQUIRED")
    expected = checks.get("installed" if envelope.operation == "execute" else "baseline")
    require(isinstance(expected, list) and 0 < len(expected) <= 12, "REQUEST_HTTP_CHECKS_INVALID")
    observations = proofs.get("http")
    require(isinstance(observations, list) and len(observations) == len(expected), "HTTP_PROOF_COUNT")
    seen: set[str] = set()
    for actual, wanted in zip(observations, expected):
        _object(actual, "http_observation")
        _object(wanted, "http_check")
        url = wanted.get("url")
        require(isinstance(url, str) and url.startswith(("https://www.uaart.com.ua/", "https://uaart.com.ua/"))
                and url not in seen and actual.get("url") == url, "HTTP_PROOF_URL")
        seen.add(url)
        require(type(wanted.get("status")) is int and 100 <= wanted["status"] <= 599
                and type(actual.get("status")) is int and actual["status"] == wanted["status"], "HTTP_PROOF_STATUS")
        require_sha(actual.get("body_sha256"), "http_body")
        if wanted.get("body_sha256") is not None:
            require(actual["body_sha256"] == require_sha(wanted["body_sha256"], "expected_http_body"), "HTTP_PROOF_BODY")
        require(type(actual.get("observed_epoch")) in (int, float) and actual["observed_epoch"] > 0,
                "HTTP_OBSERVATION_TIME_REQUIRED")


def _verify_rollback_readiness(proofs: Mapping[str, Any], backup_sha: str) -> None:
    readiness = _object(proofs.get("rollback_readiness"), "rollback_readiness")
    require(readiness.get("status") == "PASS" and
            readiness.get("scope") == "BACKUP_AND_CODE_RESTORE_READINESS_VERIFIED" and
            readiness.get("backup_manifest_sha256") == backup_sha and
            readiness.get("code_backup_manifest_sha256") == proofs["backup"]["code_manifest_sha256"] and
            readiness.get("code_restore_performed") is False and readiness.get("database_restored") is False,
            "ROLLBACK_READINESS_NOT_PROVEN")
    counts = _object(readiness.get("deletion_state_counts"), "rollback_deletion_state_counts")
    require(set(counts) == DELETION_TABLES and all(type(count) is int and count >= 0 for count in counts.values())
            and counts["ua_delete_intents"] == 0, "INTENT_AWARE_ROLLBACK_READINESS_REQUIRED")
    require(type(readiness.get("checked_epoch")) in (int, float) and readiness["checked_epoch"] > 0,
            "ROLLBACK_READINESS_OBSERVATION_REQUIRED")


def receipt_from_result(envelope: Envelope, result: Mapping[str, Any]) -> dict[str, Any]:
    """Map independently verified remote proofs to the existing strict schemas.

    Status words alone are never sufficient. Mock/fixture/offline results and
    partial phases have no successful receipt. This does not itself authenticate
    the transport; that remains the caller's exact context/source readback gate.
    """
    _object(result, "remote_result")
    require(not envelope.receipt_path.exists() and not envelope.receipt_path.is_symlink(), "RECEIPT_PREEXISTING")
    require(result.get("schema_version") == REMOTE_RESULT_SCHEMA and result.get("status") == "PASS"
            and result.get("execution_origin") == "LIVE_REMOTE_READBACK" and result.get("safe_to_stop") is True,
            "REMOTE_RESULT_NOT_PROVEN")
    require(result.get("operation") == envelope.operation and result.get("task_id") == TASK_ID
            and result.get("parent_task_id") == PARENT_TASK_ID
            and result.get("scope") == RECEIPT_SCOPE
            and result.get("live_telegram_action_verified") is False, "REMOTE_RESULT_SCOPE")
    phase = {"backup": "BACKUP_VERIFIED", "execute": "COMPLETE", "rollback": "ROLLED_BACK"}[envelope.operation]
    require(result.get("phase_status") == phase, "REMOTE_RESULT_NOT_TERMINAL")
    require(result.get("workflow_run_id") == envelope.run_id, "REMOTE_RESULT_RUN_BINDING")
    for key, expected in (("request_sha256", envelope.request_sha256), ("manifest_sha256", envelope.manifest_sha256),
                          ("transaction_id", envelope.transaction_id), ("package_manifest_sha256", envelope.package_manifest_sha256),
                          ("installation_policy_sha256", envelope.installation_policy_sha256)):
        require(result.get(key) == expected and isinstance(result.get(key), str), "REMOTE_RESULT_BINDING:" + key)
    require_sha(result.get("context_sha256"), "remote_context")
    require(type(result.get("unexpected_changes")) is int and result["unexpected_changes"] == 0,
            "REMOTE_UNEXPECTED_CHANGES")
    backup_sha = require_sha(result.get("backup_manifest_sha256"), "result_backup_manifest")
    if envelope.backup_manifest_sha256 is not None:
        require(backup_sha == envelope.backup_manifest_sha256, "REMOTE_BACKUP_BINDING")
    proofs = _object(result.get("proofs"), "remote_proofs")
    release = _release_proof(envelope, proofs)
    _verify_backup_proof(envelope, proofs, backup_sha, release)
    _verify_files_and_preservation(envelope, proofs, release)
    schema_sha = _verify_schema_proof(envelope, proofs, release)
    _verify_live_proof(envelope, proofs, release)
    if envelope.operation == "execute":
        _verify_rollback_readiness(proofs, backup_sha)
    bindings = _bindings(envelope, backup_sha)
    if envelope.operation == "backup":
        return dict(bindings, schema_version=BACKUP_RECEIPT_SCHEMA, operation="backup", status="PASS",
                    backup="PASS", unexpected_changes=0)
    if envelope.operation == "rollback":
        return dict(bindings, schema_version=ROLLBACK_RECEIPT_SCHEMA, operation="rollback", status="ROLLED_BACK",
                    rollback="PASS", restored=True, unexpected_changes=0, protected_files_unchanged=True,
                    crm_unchanged=True, live_verify="PASS")
    return dict(bindings, contract_id=CRITICAL_CONTRACT, status="FINISHED", task_class="CRITICAL",
                target_environment="production", production_required=True, production="PASS", tests="PASS",
                backup=backup_sha, rollback="PASS", rollback_ready=True,
                rollback_scope="BACKUP_AND_CODE_RESTORE_READINESS_VERIFIED", rollback_performed=False,
                live_verify="PASS", unexpected_changes=0,
                receipt_scope=RECEIPT_SCOPE, parent_task_id=PARENT_TASK_ID, parent_status=PARENT_PENDING,
                live_telegram_action_verified=False, crm_unchanged=True, protected_files_unchanged=True,
                public_or_media_writes=0, database_restored=False,
                package_manifest_sha256=envelope.package_manifest_sha256,
                installation_policy_sha256=envelope.installation_policy_sha256,
                database_digest_scope="sqlite_schema", deletion_schema_sha256=schema_sha,
                evidence_sha256=sha(canonical_json(result)))
