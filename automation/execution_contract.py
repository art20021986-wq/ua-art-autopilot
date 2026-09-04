#!/usr/bin/env python3
"""Reusable execution contract for permanent UA ART class workflows.

A task may provide Python implementation/tests, but no task-specific workflow.
This module validates immutable file hashes, class routing, evidence scope and
final receipts, then runs only argv-safe Python files. It never uses a shell for
implementation execution and never invents FINISHED.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORCHESTRATOR_PATH = ROOT / "automation/task_orchestrator.py"
ALLOWED_CONTROLLER_ROOTS = (
    ROOT / "cloud",
    ROOT / "automation/packages",
)
ALLOWED_EVIDENCE_ROOTS = (
    ROOT / "cloud",
    ROOT / "state/receipts",
)
SPECIAL_EVIDENCE = {
    (ROOT / "cloud/latest_status.md").resolve(strict=False),
    (ROOT / "cloud/owner_reply.md").resolve(strict=False),
}
DENIED_IMPORTS = {"pty", "telnetlib"}
DENIED_CALLS = {"eval", "exec"}
BACKUP_RECEIPT_SCHEMA = "UA-ART-PRODUCTION-BACKUP-RECEIPT-1"
ROLLBACK_RECEIPT_SCHEMA = "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1"
RECEIPT_BINDING_KEYS = {
    "task_id",
    "request_sha256",
    "run_id",
    "transaction_id",
    "manifest_sha256",
    "backup_manifest_sha256",
}
BACKUP_RECEIPT_KEYS = RECEIPT_BINDING_KEYS | {
    "schema_version",
    "operation",
    "status",
    "backup",
    "unexpected_changes",
}
ROLLBACK_RECEIPT_KEYS = RECEIPT_BINDING_KEYS | {
    "schema_version",
    "operation",
    "status",
    "rollback",
    "restored",
    "unexpected_changes",
    "protected_files_unchanged",
    "crm_unchanged",
    "live_verify",
}


class ExecutionContractError(ValueError):
    pass


def load_orchestrator():
    spec = importlib.util.spec_from_file_location(
        "uaart_execution_orchestrator", ORCHESTRATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("ORCHESTRATOR_SPEC")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


orchestrator = load_orchestrator()


def safe_repo_path(value: str) -> str:
    path = pathlib.PurePosixPath(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ExecutionContractError("UNSAFE_REPO_PATH:" + str(value))
    return path.as_posix()


def absolute_repo_path(value: str) -> pathlib.Path:
    normalized = safe_repo_path(value)
    resolved = (ROOT / normalized).resolve(strict=False)
    if resolved == ROOT or not resolved.is_relative_to(ROOT):
        raise ExecutionContractError("PATH_ESCAPE:" + normalized)
    return resolved


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def require_sha(value: Any, label: str) -> str:
    text = str(value or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ExecutionContractError("INVALID_SHA256:" + label)
    return text


def is_under(path: pathlib.Path, roots: Sequence[pathlib.Path]) -> bool:
    resolved = path.resolve(strict=False)
    return any(
        resolved == root.resolve(strict=False)
        or resolved.is_relative_to(root.resolve(strict=False))
        for root in roots
    )


def inspect_python(path: pathlib.Path) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in DENIED_IMPORTS:
                    raise ExecutionContractError(
                        "DENIED_IMPORT:%s:%s" % (path, alias.name)
                    )
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in DENIED_IMPORTS:
                raise ExecutionContractError(
                    "DENIED_IMPORT:%s:%s" % (path, node.module)
                )
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DENIED_CALLS:
                raise ExecutionContractError(
                    "DENIED_CALL:%s:%s" % (path, node.func.id)
                )
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr in {"system", "popen"}
            ):
                raise ExecutionContractError(
                    "DENIED_OS_EXECUTION:%s:%s" % (path, node.func.attr)
                )
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
                    if keyword.value.value is True:
                        raise ExecutionContractError("SHELL_TRUE_FORBIDDEN:" + str(path))


@dataclass(frozen=True)
class ExecutionSpec:
    request_path: str
    request_sha256: str
    task_id: str
    task_class: str
    controller_path: str
    controller_sha256: str
    test_paths: tuple[str, ...]
    file_sha256: Mapping[str, str]
    receipt_path: str
    evidence_paths: tuple[str, ...]
    backup_controller_path: str | None
    backup_controller_sha256: str | None
    backup_receipt_path: str | None
    rollback_controller_path: str | None
    rollback_controller_sha256: str | None
    rollback_receipt_path: str | None
    critical_manifest_sha256: str | None
    production_required: bool
    timeout_seconds: int
    plan: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_path": self.request_path,
            "request_sha256": self.request_sha256,
            "task_id": self.task_id,
            "task_class": self.task_class,
            "controller_path": self.controller_path,
            "controller_sha256": self.controller_sha256,
            "test_paths": list(self.test_paths),
            "file_sha256": dict(self.file_sha256),
            "receipt_path": self.receipt_path,
            "evidence_paths": list(self.evidence_paths),
            "backup_controller_path": self.backup_controller_path,
            "backup_controller_sha256": self.backup_controller_sha256,
            "backup_receipt_path": self.backup_receipt_path,
            "rollback_controller_path": self.rollback_controller_path,
            "rollback_controller_sha256": self.rollback_controller_sha256,
            "rollback_receipt_path": self.rollback_receipt_path,
            "critical_manifest_sha256": self.critical_manifest_sha256,
            "production_required": self.production_required,
            "timeout_seconds": self.timeout_seconds,
            "plan": dict(self.plan),
        }


def load_request(request_path: str) -> tuple[pathlib.Path, dict[str, Any]]:
    normalized = safe_repo_path(request_path)
    if not normalized.startswith("tasks/requests/") or not normalized.endswith(".json"):
        raise ExecutionContractError("REQUEST_PATH_SCOPE")
    path = absolute_repo_path(normalized)
    if path.is_symlink() or not path.is_file():
        raise ExecutionContractError("REQUEST_FILE_MISSING")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ExecutionContractError("REQUEST_NOT_OBJECT")
    return path, raw


def validate_auxiliary_contract(
    execution: Mapping[str, Any],
    operation: str,
    package_root: pathlib.Path,
    primary_receipt_path: str,
) -> tuple[str | None, str | None, str | None]:
    prefix = operation.lower()
    values = (
        execution.get(prefix + "_controller_path"),
        execution.get(prefix + "_controller_sha256"),
        execution.get(prefix + "_receipt_path"),
    )
    if not any(value not in (None, "") for value in values):
        return None, None, None
    if any(value in (None, "") for value in values):
        raise ExecutionContractError(operation.upper() + "_CONTRACT_INCOMPLETE")
    controller_path = safe_repo_path(str(values[0]))
    controller = absolute_repo_path(controller_path)
    if not is_under(controller, ALLOWED_CONTROLLER_ROOTS):
        raise ExecutionContractError(operation.upper() + "_CONTROLLER_SCOPE")
    if (
        controller.suffix != ".py"
        or controller.is_symlink()
        or not controller.is_file()
        or not controller.resolve(strict=True).is_relative_to(package_root)
    ):
        raise ExecutionContractError(operation.upper() + "_CONTROLLER_FILE")
    controller_sha256 = require_sha(values[1], prefix + "_controller")
    if sha256_file(controller) != controller_sha256:
        raise ExecutionContractError(operation.upper() + "_CONTROLLER_SHA_MISMATCH")
    inspect_python(controller)
    receipt_path = safe_repo_path(str(values[2]))
    if (
        not receipt_path.startswith("state/receipts/")
        or not receipt_path.endswith(".json")
        or receipt_path == primary_receipt_path
    ):
        raise ExecutionContractError(operation.upper() + "_RECEIPT_SCOPE")
    return controller_path, controller_sha256, receipt_path


def validate_execution(
    request_path: str,
    expected_class: str,
) -> ExecutionSpec:
    request_file, raw = load_request(request_path)
    request_sha256 = sha256_file(request_file)
    request = orchestrator.TaskRequest.from_mapping(raw)
    plan = orchestrator.build_plan(request).to_dict()
    expected = str(expected_class).upper()
    if expected not in {item.value for item in orchestrator.TaskClass}:
        raise ExecutionContractError("EXPECTED_CLASS_INVALID")
    if plan["task_class"] != expected:
        raise ExecutionContractError(
            "ROUTE_CLASS_MISMATCH:%s:%s" % (expected, plan["task_class"])
        )

    execution = raw.get("execution")
    if not isinstance(execution, dict):
        raise ExecutionContractError("EXECUTION_OBJECT_REQUIRED")
    controller_path = safe_repo_path(str(execution.get("controller_path", "")))
    controller = absolute_repo_path(controller_path)
    if not is_under(controller, ALLOWED_CONTROLLER_ROOTS):
        raise ExecutionContractError("CONTROLLER_SCOPE")
    if controller.suffix != ".py" or controller.is_symlink() or not controller.is_file():
        raise ExecutionContractError("CONTROLLER_FILE")
    controller_sha = require_sha(
        execution.get("controller_sha256"), "controller"
    )
    if sha256_file(controller) != controller_sha:
        raise ExecutionContractError("CONTROLLER_SHA_MISMATCH")
    inspect_python(controller)

    tests_raw = execution.get("test_paths")
    if not isinstance(tests_raw, list) or not tests_raw or len(tests_raw) > 20:
        raise ExecutionContractError("TEST_PATHS_RANGE")
    tests = tuple(safe_repo_path(str(value)) for value in tests_raw)
    file_hashes_raw = execution.get("file_sha256")
    if not isinstance(file_hashes_raw, dict):
        raise ExecutionContractError("FILE_SHA256_OBJECT_REQUIRED")
    file_hashes: dict[str, str] = {}
    package_root = controller.parent.resolve(strict=True)
    for item in tests:
        test_path = absolute_repo_path(item)
        if test_path.suffix != ".py" or test_path.is_symlink() or not test_path.is_file():
            raise ExecutionContractError("TEST_FILE:" + item)
        if not test_path.resolve(strict=True).is_relative_to(package_root):
            raise ExecutionContractError("TEST_PACKAGE_SCOPE:" + item)
        expected_sha = require_sha(file_hashes_raw.get(item), "test:" + item)
        if sha256_file(test_path) != expected_sha:
            raise ExecutionContractError("TEST_SHA_MISMATCH:" + item)
        file_hashes[item] = expected_sha
        inspect_python(test_path)

    receipt_path = safe_repo_path(str(execution.get("receipt_path", "")))
    receipt = absolute_repo_path(receipt_path)
    if not receipt_path.startswith("state/receipts/") or not receipt_path.endswith(".json"):
        raise ExecutionContractError("RECEIPT_SCOPE")

    (
        backup_controller_path,
        backup_controller_sha256,
        backup_receipt_path,
    ) = validate_auxiliary_contract(execution, "backup", package_root, receipt_path)
    (
        rollback_controller_path,
        rollback_controller_sha256,
        rollback_receipt_path,
    ) = validate_auxiliary_contract(execution, "rollback", package_root, receipt_path)
    if (
        backup_receipt_path is not None
        and backup_receipt_path == rollback_receipt_path
    ):
        raise ExecutionContractError("BACKUP_ROLLBACK_RECEIPT_COLLISION")

    evidence_raw = execution.get("evidence_paths")
    if not isinstance(evidence_raw, list) or not evidence_raw or len(evidence_raw) > 30:
        raise ExecutionContractError("EVIDENCE_PATHS_RANGE")
    evidence_paths = tuple(sorted({safe_repo_path(str(value)) for value in evidence_raw}))
    if receipt_path not in evidence_paths:
        raise ExecutionContractError("RECEIPT_NOT_IN_EVIDENCE")
    for item in evidence_paths:
        path = absolute_repo_path(item)
        if path in SPECIAL_EVIDENCE:
            continue
        if not is_under(path, ALLOWED_EVIDENCE_ROOTS):
            raise ExecutionContractError("EVIDENCE_SCOPE:" + item)
        if path.is_relative_to((ROOT / "state/receipts").resolve(strict=False)):
            if item not in {receipt_path, backup_receipt_path, rollback_receipt_path}:
                raise ExecutionContractError("EXTRA_RECEIPT_SCOPE:" + item)
        elif not path.is_relative_to(package_root):
            raise ExecutionContractError("EVIDENCE_PACKAGE_SCOPE:" + item)

    production_required = bool(raw.get("production_required", False))
    if bool(execution.get("production_required", production_required)) != production_required:
        raise ExecutionContractError("EXECUTION_PRODUCTION_MISMATCH")
    if production_required and expected != "CRITICAL":
        raise ExecutionContractError("PRODUCTION_MUST_ROUTE_CRITICAL")
    if production_required and backup_controller_path is None:
        raise ExecutionContractError("PRODUCTION_BACKUP_CONTRACT_REQUIRED")
    if production_required and rollback_controller_path is None:
        raise ExecutionContractError("PRODUCTION_ROLLBACK_CONTRACT_REQUIRED")
    if backup_receipt_path is not None and backup_receipt_path not in evidence_paths:
        raise ExecutionContractError("BACKUP_RECEIPT_NOT_IN_EVIDENCE")
    if rollback_receipt_path is not None and rollback_receipt_path not in evidence_paths:
        raise ExecutionContractError("ROLLBACK_RECEIPT_NOT_IN_EVIDENCE")
    timeout_seconds = int(execution.get("timeout_seconds", 1200))
    if timeout_seconds < 10 or timeout_seconds > 3600:
        raise ExecutionContractError("TIMEOUT_RANGE")
    if expected == "FAST" and len(request.changed_paths) > 3:
        raise ExecutionContractError("FAST_PATH_COUNT")
    if expected == "CRITICAL" and not raw.get("critical"):
        raise ExecutionContractError("CRITICAL_GATE_OBJECT_REQUIRED")

    critical_manifest_sha256 = None
    if production_required:
        critical = raw.get("critical")
        if not isinstance(critical, dict):
            raise ExecutionContractError("CRITICAL_GATE_OBJECT_REQUIRED")
        critical_manifest_sha256 = require_sha(
            critical.get("manifest_sha256"), "critical_manifest"
        )

    file_hashes[controller_path] = controller_sha
    if backup_controller_path is not None:
        file_hashes[backup_controller_path] = str(backup_controller_sha256)
    if rollback_controller_path is not None:
        file_hashes[rollback_controller_path] = str(rollback_controller_sha256)
    return ExecutionSpec(
        request_path=safe_repo_path(request_path),
        request_sha256=request_sha256,
        task_id=request.task_id,
        task_class=expected,
        controller_path=controller_path,
        controller_sha256=controller_sha,
        test_paths=tests,
        file_sha256=file_hashes,
        receipt_path=receipt_path,
        evidence_paths=evidence_paths,
        backup_controller_path=backup_controller_path,
        backup_controller_sha256=backup_controller_sha256,
        backup_receipt_path=backup_receipt_path,
        rollback_controller_path=rollback_controller_path,
        rollback_controller_sha256=rollback_controller_sha256,
        rollback_receipt_path=rollback_receipt_path,
        critical_manifest_sha256=critical_manifest_sha256,
        production_required=production_required,
        timeout_seconds=timeout_seconds,
        plan=plan,
    )


def compile_spec(spec: ExecutionSpec) -> None:
    items = [spec.controller_path, *spec.test_paths]
    if spec.backup_controller_path is not None:
        items.append(spec.backup_controller_path)
    if spec.rollback_controller_path is not None:
        items.append(spec.rollback_controller_path)
    for item in items:
        path = absolute_repo_path(item)
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def run_tests(spec: ExecutionSpec) -> None:
    for item in spec.test_paths:
        completed = subprocess.run(
            [sys.executable, str(absolute_repo_path(item))],
            cwd=ROOT,
            check=False,
            timeout=min(spec.timeout_seconds, 600),
        )
        if completed.returncode != 0:
            raise ExecutionContractError("TEST_FAILED:" + item)


def require_receipt_target_absent(receipt_path: str | None, operation: str) -> None:
    if receipt_path is None:
        raise ExecutionContractError(operation.upper() + "_RECEIPT_REQUIRED")
    path = absolute_repo_path(receipt_path)
    if path.is_symlink() or path.exists():
        raise ExecutionContractError(operation.upper() + "_RECEIPT_PREEXISTING")


def require_environment_value(environment: Mapping[str, str], key: str) -> str:
    value = str(environment.get(key, ""))
    if not value or len(value) > 256 or any(character in value for character in "\r\n\0"):
        raise ExecutionContractError("RUNTIME_BINDING_INVALID:" + key)
    return value


def production_operation_environment(
    spec: ExecutionSpec,
    operation: str,
    receipt_path: str,
    *,
    backup_manifest_sha256: str | None = None,
) -> dict[str, str]:
    if not spec.production_required or spec.critical_manifest_sha256 is None:
        raise ExecutionContractError("PRODUCTION_OPERATION_REQUIRED:" + operation)
    environment = dict(os.environ)
    require_environment_value(environment, "UAART_RUN_ID")
    require_environment_value(environment, "UAART_TRANSACTION_ID")
    supplied_request_sha = environment.get("UAART_REQUEST_SHA256")
    if supplied_request_sha not in (None, "") and supplied_request_sha != spec.request_sha256:
        raise ExecutionContractError("RUNTIME_REQUEST_SHA256_MISMATCH")
    supplied_manifest_sha = environment.get("UAART_MANIFEST_SHA256")
    if (
        supplied_manifest_sha not in (None, "")
        and supplied_manifest_sha != spec.critical_manifest_sha256
    ):
        raise ExecutionContractError("RUNTIME_MANIFEST_SHA256_MISMATCH")
    environment.update(
        {
            "UAART_OPERATION": operation,
            "UAART_RECEIPT_PATH": receipt_path,
            "UAART_REQUEST_PATH": spec.request_path,
            "UAART_REQUEST_SHA256": spec.request_sha256,
            "UAART_TASK_ID": spec.task_id,
            "UAART_MANIFEST_SHA256": spec.critical_manifest_sha256,
        }
    )
    if backup_manifest_sha256 is not None:
        environment["UAART_BACKUP_MANIFEST_SHA256"] = require_sha(
            backup_manifest_sha256, "runtime_backup_manifest"
        )
    return environment


def run_controller(spec: ExecutionSpec) -> None:
    require_receipt_target_absent(spec.receipt_path, "controller")
    environment = dict(os.environ)
    if spec.production_required:
        backup_receipt = validate_backup_receipt(spec)
        environment = production_operation_environment(
            spec,
            "execute",
            spec.receipt_path,
            backup_manifest_sha256=backup_receipt["backup_manifest_sha256"],
        )
    completed = subprocess.run(
        [sys.executable, str(absolute_repo_path(spec.controller_path))],
        cwd=ROOT,
        check=False,
        timeout=spec.timeout_seconds,
        env=environment,
    )
    if completed.returncode != 0:
        raise ExecutionContractError("CONTROLLER_FAILED:%d" % completed.returncode)


def run_backup(spec: ExecutionSpec) -> None:
    if spec.backup_controller_path is None:
        raise ExecutionContractError("BACKUP_CONTROLLER_REQUIRED")
    require_receipt_target_absent(spec.backup_receipt_path, "backup")
    environment = production_operation_environment(
        spec, "backup", str(spec.backup_receipt_path)
    )
    environment["UAART_BACKUP_RECEIPT_PATH"] = str(spec.backup_receipt_path)
    completed = subprocess.run(
        [sys.executable, str(absolute_repo_path(spec.backup_controller_path))],
        cwd=ROOT,
        check=False,
        timeout=spec.timeout_seconds,
        env=environment,
    )
    if completed.returncode != 0:
        raise ExecutionContractError("BACKUP_CONTROLLER_FAILED:%d" % completed.returncode)


def run_rollback(spec: ExecutionSpec) -> None:
    if spec.rollback_controller_path is None:
        raise ExecutionContractError("ROLLBACK_CONTROLLER_REQUIRED")
    require_receipt_target_absent(spec.rollback_receipt_path, "rollback")
    backup_receipt = validate_backup_receipt(spec)
    supplied_backup_sha = require_sha(
        os.environ.get("UAART_BACKUP_MANIFEST_SHA256"),
        "runtime_backup_manifest",
    )
    if supplied_backup_sha != backup_receipt["backup_manifest_sha256"]:
        raise ExecutionContractError("RUNTIME_BACKUP_MANIFEST_SHA256_MISMATCH")
    environment = production_operation_environment(
        spec,
        "rollback",
        str(spec.rollback_receipt_path),
        backup_manifest_sha256=supplied_backup_sha,
    )
    environment["UAART_ROLLBACK_RECEIPT_PATH"] = str(spec.rollback_receipt_path)
    completed = subprocess.run(
        [sys.executable, str(absolute_repo_path(spec.rollback_controller_path))],
        cwd=ROOT,
        check=False,
        timeout=spec.timeout_seconds,
        env=environment,
    )
    if completed.returncode != 0:
        raise ExecutionContractError("ROLLBACK_CONTROLLER_FAILED:%d" % completed.returncode)


def read_strict_receipt(
    receipt_path: str | None,
    operation: str,
    expected_keys: set[str],
) -> dict[str, Any]:
    if receipt_path is None:
        raise ExecutionContractError(operation.upper() + "_RECEIPT_REQUIRED")
    path = absolute_repo_path(receipt_path)
    if path.is_symlink() or not path.is_file():
        raise ExecutionContractError(operation.upper() + "_RECEIPT_MISSING")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionContractError(operation.upper() + "_RECEIPT_INVALID_JSON") from exc
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ExecutionContractError(operation.upper() + "_RECEIPT_SCHEMA_KEYS")
    return value


def validate_receipt_bindings(
    spec: ExecutionSpec,
    value: Mapping[str, Any],
    operation: str,
    *,
    expected_backup_manifest_sha256: str | None = None,
) -> str:
    environment = dict(os.environ)
    expected = {
        "task_id": spec.task_id,
        "request_sha256": spec.request_sha256,
        "run_id": require_environment_value(environment, "UAART_RUN_ID"),
        "transaction_id": require_environment_value(
            environment, "UAART_TRANSACTION_ID"
        ),
        "manifest_sha256": spec.critical_manifest_sha256,
    }
    for key, expected_value in expected.items():
        if not isinstance(value.get(key), str) or value.get(key) != expected_value:
            raise ExecutionContractError(
                operation.upper() + "_RECEIPT_BINDING_" + key.upper()
            )
    backup_manifest_sha256 = require_sha(
        value.get("backup_manifest_sha256"), operation + "_backup_manifest"
    )
    if (
        expected_backup_manifest_sha256 is not None
        and backup_manifest_sha256 != expected_backup_manifest_sha256
    ):
        raise ExecutionContractError(
            operation.upper() + "_RECEIPT_BACKUP_MANIFEST_SHA256_MISMATCH"
        )
    return backup_manifest_sha256


def validate_backup_receipt(spec: ExecutionSpec) -> dict[str, Any]:
    value = read_strict_receipt(
        spec.backup_receipt_path, "backup", BACKUP_RECEIPT_KEYS
    )
    if value.get("schema_version") != BACKUP_RECEIPT_SCHEMA:
        raise ExecutionContractError("BACKUP_RECEIPT_SCHEMA_VERSION")
    if value.get("operation") != "backup":
        raise ExecutionContractError("BACKUP_RECEIPT_OPERATION")
    if value.get("status") != "PASS" or value.get("backup") != "PASS":
        raise ExecutionContractError("BACKUP_RECEIPT_STATUS")
    if type(value.get("unexpected_changes")) is not int or value.get(
        "unexpected_changes"
    ) != 0:
        raise ExecutionContractError("BACKUP_RECEIPT_UNEXPECTED_CHANGES")
    value["backup_manifest_sha256"] = validate_receipt_bindings(
        spec, value, "backup"
    )
    return value


def validate_rollback_receipt(spec: ExecutionSpec) -> dict[str, Any]:
    value = read_strict_receipt(
        spec.rollback_receipt_path, "rollback", ROLLBACK_RECEIPT_KEYS
    )
    if value.get("schema_version") != ROLLBACK_RECEIPT_SCHEMA:
        raise ExecutionContractError("ROLLBACK_RECEIPT_SCHEMA_VERSION")
    if value.get("operation") != "rollback":
        raise ExecutionContractError("ROLLBACK_RECEIPT_OPERATION")
    if value.get("status") not in {"PASS", "ROLLED_BACK"}:
        raise ExecutionContractError("ROLLBACK_RECEIPT_STATUS")
    if value.get("rollback") != "PASS" or value.get("restored") is not True:
        raise ExecutionContractError("ROLLBACK_RECEIPT_NOT_PROVEN")
    if type(value.get("unexpected_changes")) is not int or value.get(
        "unexpected_changes"
    ) != 0:
        raise ExecutionContractError("ROLLBACK_RECEIPT_UNEXPECTED_CHANGES")
    if value.get("protected_files_unchanged") is not True:
        raise ExecutionContractError("ROLLBACK_RECEIPT_PROTECTED_DRIFT")
    if value.get("crm_unchanged") is not True or value.get("live_verify") != "PASS":
        raise ExecutionContractError("ROLLBACK_RECEIPT_LIVE_INTEGRITY")
    expected_backup_manifest_sha256 = require_sha(
        os.environ.get("UAART_BACKUP_MANIFEST_SHA256"),
        "runtime_backup_manifest",
    )
    value["backup_manifest_sha256"] = validate_receipt_bindings(
        spec,
        value,
        "rollback",
        expected_backup_manifest_sha256=expected_backup_manifest_sha256,
    )
    return value


def validate_receipt(spec: ExecutionSpec) -> dict[str, Any]:
    path = absolute_repo_path(spec.receipt_path)
    if path.is_symlink() or not path.is_file():
        raise ExecutionContractError("RECEIPT_MISSING")
    raw = json.loads(path.read_text(encoding="utf-8"))
    value = orchestrator.validate_receipt(raw)
    if value.get("task_id") != spec.task_id:
        raise ExecutionContractError("RECEIPT_TASK_ID")
    if str(value.get("task_class", "")).upper() != spec.task_class:
        raise ExecutionContractError("RECEIPT_CLASS")
    if bool(value.get("production_required")) != spec.production_required:
        raise ExecutionContractError("RECEIPT_PRODUCTION_FLAG")
    return value


def stage_evidence(spec: ExecutionSpec) -> list[str]:
    existing = []
    for item in spec.evidence_paths:
        path = absolute_repo_path(item)
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise ExecutionContractError("EVIDENCE_NOT_REGULAR:" + item)
            existing.append(item)
    if spec.receipt_path not in existing:
        raise ExecutionContractError("RECEIPT_NOT_CREATED")
    for item in existing:
        completed = subprocess.run(
            ["git", "add", "--", item], cwd=ROOT, check=False
        )
        if completed.returncode != 0:
            raise ExecutionContractError("GIT_ADD_FAILED:" + item)
    return existing


def write_github_output(spec: ExecutionSpec) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        raise ExecutionContractError("GITHUB_OUTPUT_MISSING")
    with open(target, "a", encoding="utf-8") as handle:
        handle.write("task_id=%s\n" % spec.task_id)
        handle.write("task_class=%s\n" % spec.task_class)
        handle.write("controller_path=%s\n" % spec.controller_path)
        handle.write("receipt_path=%s\n" % spec.receipt_path)
        handle.write("request_sha256=%s\n" % spec.request_sha256)
        handle.write("backup_controller_path=%s\n" % (spec.backup_controller_path or ""))
        handle.write("backup_receipt_path=%s\n" % (spec.backup_receipt_path or ""))
        handle.write("rollback_controller_path=%s\n" % (spec.rollback_controller_path or ""))
        handle.write("rollback_receipt_path=%s\n" % (spec.rollback_receipt_path or ""))
        handle.write(
            "critical_manifest_sha256=%s\n"
            % (spec.critical_manifest_sha256 or "")
        )
        handle.write("production_required=%s\n" % str(spec.production_required).lower())
        handle.write("timeout_seconds=%d\n" % spec.timeout_seconds)
        handle.write("ai_route=%s\n" % spec.plan["ai_route"])
        handle.write("ai_call_budget=%d\n" % spec.plan["ai_call_budget"])


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "compile",
            "test",
            "backup",
            "backup-receipt",
            "run",
            "rollback",
            "rollback-receipt",
            "receipt",
            "stage",
            "outputs",
        ),
    )
    parser.add_argument("request_path")
    parser.add_argument("--expected-class", required=True)
    args = parser.parse_args()
    spec = validate_execution(args.request_path, args.expected_class)
    if args.command == "validate":
        _dump(spec.to_dict())
    elif args.command == "compile":
        compile_spec(spec)
        _dump({"status": "PASS", "compiled": [spec.controller_path, *spec.test_paths]})
    elif args.command == "test":
        run_tests(spec)
        _dump({"status": "PASS", "tests": list(spec.test_paths)})
    elif args.command == "backup":
        run_backup(spec)
        _dump({"status": "PASS", "backup_controller": spec.backup_controller_path})
    elif args.command == "backup-receipt":
        _dump(validate_backup_receipt(spec))
    elif args.command == "run":
        run_controller(spec)
        _dump({"status": "PASS", "controller": spec.controller_path})
    elif args.command == "rollback":
        run_rollback(spec)
        _dump({"status": "PASS", "rollback_controller": spec.rollback_controller_path})
    elif args.command == "rollback-receipt":
        _dump(validate_rollback_receipt(spec))
    elif args.command == "receipt":
        _dump(validate_receipt(spec))
    elif args.command == "stage":
        _dump({"status": "PASS", "staged": stage_evidence(spec)})
    else:
        write_github_output(spec)
        _dump({"status": "PASS", "outputs": True})


if __name__ == "__main__":
    main()
