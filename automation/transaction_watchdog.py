#!/usr/bin/env python3
"""Discover and strictly validate one durable Production transaction.

The workflow using this module shares the global Production concurrency key.
It may expose a Production rollback credential only for one fully validated
``OPEN`` transaction.  ``PREPARING`` is visible but never credential-eligible;
``ROLLING_BACK`` means the one automatic rollback attempt was already consumed,
so recovery must halt for manual reconciliation and must not retry it.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import sys
from typing import Any, Mapping

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_control_plane():
    """Load the pinned sibling explicitly so the CLI works under Python ``-I``."""
    path = ROOT / "automation/control_plane.py"
    spec = importlib.util.spec_from_file_location("uaart_watchdog_control_plane", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CONTROL_PLANE_SPEC")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cp = _load_control_plane()
EXPECTED_KEYS = {
    "autostart_ledger_path",
    "backup_manifest_sha256",
    "backup_receipt_path",
    "backup_receipt_sha256",
    "expires_at",
    "mode_epoch",
    "opened_at",
    "prepared_at",
    "request_path",
    "request_sha256",
    "run_id",
    "schema_version",
    "status",
    "task_id",
    "transaction_id",
}
PENDING_STATUSES = frozenset({"PREPARING", "OPEN", "ROLLING_BACK"})
TERMINAL_STATUSES = frozenset({"FINISHED", "ROLLED_BACK"})
BACKUP_RECEIPT_KEYS = {
    "backup",
    "backup_manifest_sha256",
    "manifest_sha256",
    "operation",
    "request_sha256",
    "run_id",
    "schema_version",
    "status",
    "task_id",
    "transaction_id",
    "unexpected_changes",
}


class WatchdogError(ValueError):
    """A fail-closed watchdog validation error."""


def _output(values: Mapping[str, Any]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            text = str(value)
            if "\n" in text or "\r" in text:
                raise WatchdogError("MULTILINE_OUTPUT:" + key)
            handle.write(f"{key}={text}\n")


def _relative_file(
    relative: str,
    *,
    root: pathlib.Path,
    error: str,
) -> pathlib.Path:
    """Return a regular in-repository file without following a leaf symlink."""
    try:
        normalized = cp.safe_repo_path(relative)
    except cp.ControlPlaneError as exc:
        raise WatchdogError(error + "_PATH") from exc
    raw_path = root / normalized
    try:
        resolved = cp.repo_path(normalized, root)
    except cp.ControlPlaneError as exc:
        raise WatchdogError(error + "_PATH") from exc
    if raw_path.is_symlink() or resolved.is_symlink() or not resolved.is_file():
        raise WatchdogError(error)
    return resolved


def _request_and_identity(
    value: Mapping[str, Any],
    *,
    root: pathlib.Path,
) -> tuple[str, dict[str, Any], str, dict[str, str]]:
    try:
        request_rel = cp.safe_repo_path(str(value.get("request_path", "")))
        _relative_file(
            request_rel, root=root, error="TRANSACTION_REQUEST_MISSING"
        )
        normalized, request_path, raw, request_sha = cp.load_request(request_rel, root)
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_REQUEST_INVALID") from exc
    if request_path.is_symlink() or not request_path.is_file():
        raise WatchdogError("TRANSACTION_REQUEST_MISSING")
    try:
        expected_request_sha = cp.require_sha(value.get("request_sha256"), "request")
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_REQUEST_SHA") from exc
    if request_sha != expected_request_sha:
        raise WatchdogError("TRANSACTION_REQUEST_SHA")
    if normalized != request_rel:
        raise WatchdogError("TRANSACTION_REQUEST_PATH")
    if raw.get("production_required") is not True:
        raise WatchdogError("TRANSACTION_NOT_PRODUCTION")
    critical = raw.get("critical")
    if not isinstance(critical, dict) or critical.get("gate_b_authorized") is not True:
        raise WatchdogError("TRANSACTION_GATE_B_NOT_AUTHORIZED")
    try:
        cp.require_sha(critical.get("manifest_sha256"), "manifest")
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_MANIFEST_SHA") from exc
    try:
        if cp.classify_request(raw) != "CRITICAL":
            raise WatchdogError("TRANSACTION_NOT_CRITICAL")
        identity = cp._identity(raw, request_sha, str(value.get("run_id", "")))
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_IDENTITY") from exc
    if value.get("task_id") != raw.get("task_id"):
        raise WatchdogError("TRANSACTION_TASK_ID")
    return normalized, raw, request_sha, identity


def _validate_claim_and_ledger(
    value: Mapping[str, Any],
    *,
    relative: str,
    request_rel: str,
    raw: Mapping[str, Any],
    request_sha: str,
    identity: Mapping[str, str],
    root: pathlib.Path,
) -> dict[str, Any]:
    claim_rel = cp.claim_relative_path(identity)
    claim_path = _relative_file(claim_rel, root=root, error="TRANSACTION_CLAIM_MISSING")
    try:
        claim = cp.read_json(claim_path)
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_CLAIM_INVALID") from exc
    if claim.get("schema_version") != cp.SCHEMA_VERSION:
        raise WatchdogError("TRANSACTION_CLAIM_SCHEMA")
    if (
        claim.get("identity") != dict(identity)
        or claim.get("request_path") != request_rel
        or claim.get("request_sha256") != request_sha
    ):
        raise WatchdogError("TRANSACTION_CLAIM_IDENTITY")
    if claim.get("production_required") is not True:
        raise WatchdogError("TRANSACTION_CLAIM_NOT_PRODUCTION")
    if claim.get("task_class") != "CRITICAL":
        raise WatchdogError("TRANSACTION_CLAIM_NOT_CRITICAL")
    if claim.get("execution_mode") != "AUTOMATIC":
        raise WatchdogError("TRANSACTION_CLAIM_MODE")
    if claim.get("mode_epoch") != value.get("mode_epoch"):
        raise WatchdogError("TRANSACTION_CLAIM_MODE_EPOCH")
    if claim.get("critical_gate_status") != "PASS_PRODUCTION":
        raise WatchdogError("TRANSACTION_CLAIM_GATE_B")
    try:
        cp.require_sha(claim.get("critical_gate_evidence_sha256"), "gate_b_evidence")
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_CLAIM_GATE_B_EVIDENCE") from exc
    if claim.get("package_compile_status") != "PASS":
        raise WatchdogError("TRANSACTION_CLAIM_COMPILE")
    if claim.get("pre_health_status") != "PASS":
        raise WatchdogError("TRANSACTION_CLAIM_PRE_HEALTH")
    storage = claim.get("storage_preflight")
    if (
        not isinstance(storage, dict)
        or storage.get("allowed") is not True
        or claim.get("storage_preflight_status") != storage.get("status")
    ):
        raise WatchdogError("TRANSACTION_CLAIM_STORAGE")
    if (
        claim.get("production_transaction_id") != value.get("transaction_id")
        or claim.get("production_transaction_path") != relative
        or claim.get("production_transaction_status") != value.get("status")
    ):
        raise WatchdogError("TRANSACTION_CLAIM_TRANSACTION_BINDING")

    try:
        ledger_rel = cp.safe_repo_path(str(value.get("autostart_ledger_path", "")))
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_LEDGER_PATH") from exc
    if claim.get("autostart_ledger_path") != ledger_rel:
        raise WatchdogError("TRANSACTION_CLAIM_LEDGER_PATH")
    ledger_path = _relative_file(
        ledger_rel, root=root, error="TRANSACTION_LEDGER_MISSING"
    )
    source_commit = str(claim.get("autostart_source_commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise WatchdogError("TRANSACTION_CLAIM_SOURCE_COMMIT")
    try:
        binding = cp.verify_autostart_ledger(
            ledger_rel,
            request_rel,
            raw,
            request_sha,
            str(value.get("run_id", "")),
            expected_source_commit=source_commit,
            root=root,
            allow_expired_for_recovery=True,
            allow_halt_for_recovery=True,
        )
        claim_ledger_sha = cp.require_sha(
            claim.get("autostart_ledger_sha256"), "claim_autostart_ledger"
        )
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_LEDGER_INVALID") from exc
    if (
        binding.get("ledger_path") != ledger_rel
        or binding.get("source_commit") != source_commit
        or binding.get("ledger_sha256") != claim_ledger_sha
    ):
        raise WatchdogError("TRANSACTION_CLAIM_LEDGER_SHA")
    try:
        ledger = cp.read_json(ledger_path)
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_LEDGER_INVALID") from exc
    if (
        ledger.get("expires_at") != value.get("expires_at")
        or ledger.get("mode_epoch") != value.get("mode_epoch")
    ):
        raise WatchdogError("TRANSACTION_LEDGER_TRANSACTION_BINDING")
    return claim


def _validate_backup_receipt(
    value: Mapping[str, Any],
    *,
    raw: Mapping[str, Any],
    request_sha: str,
    root: pathlib.Path,
) -> None:
    execution = raw.get("execution")
    if not isinstance(execution, dict):
        raise WatchdogError("TRANSACTION_EXECUTION_OBJECT")
    try:
        backup_rel = cp.safe_repo_path(str(value.get("backup_receipt_path", "")))
        configured_rel = cp.safe_repo_path(str(execution.get("backup_receipt_path", "")))
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_BACKUP_RECEIPT_PATH") from exc
    if (
        backup_rel != configured_rel
        or not backup_rel.startswith("state/receipts/")
        or not backup_rel.endswith(".json")
    ):
        raise WatchdogError("TRANSACTION_BACKUP_RECEIPT_BINDING")
    backup_path = _relative_file(
        backup_rel, root=root, error="TRANSACTION_BACKUP_RECEIPT_MISSING"
    )
    try:
        receipt_sha = cp.require_sha(
            value.get("backup_receipt_sha256"), "backup_receipt"
        )
        backup_manifest_sha = cp.require_sha(
            value.get("backup_manifest_sha256"), "backup_manifest"
        )
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_BACKUP_SHA") from exc
    if cp.sha256_file(backup_path) != receipt_sha:
        raise WatchdogError("TRANSACTION_BACKUP_RECEIPT_SHA")
    try:
        receipt = cp.read_json(backup_path)
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_BACKUP_RECEIPT_INVALID") from exc
    critical = raw.get("critical")
    if not isinstance(critical, dict):
        raise WatchdogError("TRANSACTION_CRITICAL_OBJECT")
    try:
        manifest_sha = cp.require_sha(critical.get("manifest_sha256"), "manifest")
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_MANIFEST_SHA") from exc
    if set(receipt) != BACKUP_RECEIPT_KEYS:
        raise WatchdogError("TRANSACTION_BACKUP_RECEIPT_SCHEMA_KEYS")
    if (
        receipt.get("schema_version") != "UA-ART-PRODUCTION-BACKUP-RECEIPT-1"
        or receipt.get("operation") != "backup"
        or receipt.get("status") != "PASS"
        or receipt.get("backup") != "PASS"
        or type(receipt.get("unexpected_changes")) is not int
        or receipt.get("unexpected_changes") != 0
        or receipt.get("task_id") != raw.get("task_id")
        or receipt.get("request_sha256") != request_sha
        or str(receipt.get("run_id")) != str(value.get("run_id"))
        or receipt.get("transaction_id") != value.get("transaction_id")
        or receipt.get("manifest_sha256") != manifest_sha
        or receipt.get("backup_manifest_sha256") != backup_manifest_sha
    ):
        raise WatchdogError("TRANSACTION_BACKUP_RECEIPT_BINDING")


def validate_transaction(path: pathlib.Path, *, root: pathlib.Path = ROOT) -> dict[str, Any]:
    root = root.resolve(strict=False)
    if path.is_symlink() or not path.is_file():
        raise WatchdogError("TRANSACTION_FILE_INVALID")
    try:
        relative = path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise WatchdogError("TRANSACTION_OUTSIDE_ROOT") from exc
    if not relative.startswith("state/transactions/") or not relative.endswith(".json"):
        raise WatchdogError("TRANSACTION_PATH_SCOPE")
    try:
        value = cp.read_json(path)
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_JSON_INVALID") from exc
    if set(value) != EXPECTED_KEYS:
        raise WatchdogError("TRANSACTION_SCHEMA_KEYS")
    if value.get("schema_version") != cp.PRODUCTION_TRANSACTION_SCHEMA:
        raise WatchdogError("TRANSACTION_SCHEMA")
    status = str(value.get("status", ""))
    if status not in PENDING_STATUSES:
        raise WatchdogError("TRANSACTION_NOT_PENDING")
    transaction_id = str(value.get("transaction_id", ""))
    if not re.fullmatch(r"tx-[A-Za-z0-9._-]{16,120}", transaction_id):
        raise WatchdogError("TRANSACTION_ID")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(value.get("run_id", ""))):
        raise WatchdogError("TRANSACTION_RUN_ID")

    request_rel, raw, request_sha, identity = _request_and_identity(value, root=root)
    expected_relative = cp.transaction_relative_path(identity)
    if relative != expected_relative:
        raise WatchdogError("TRANSACTION_CANONICAL_PATH")
    try:
        mode = cp.verify_execution_mode(
            root=root,
            required_mode="AUTOMATIC",
            allow_halt_for_recovery=True,
        )
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_MODE_INVALID") from exc
    if value.get("mode_epoch") != mode.get("mode_epoch"):
        raise WatchdogError("TRANSACTION_MODE_EPOCH")

    try:
        prepared_at = cp.parse_utc(str(value.get("prepared_at", "")))
        expires_at = cp.parse_utc(str(value.get("expires_at", "")))
    except cp.ControlPlaneError as exc:
        raise WatchdogError("TRANSACTION_TIME_INVALID") from exc
    if prepared_at >= expires_at:
        raise WatchdogError("TRANSACTION_TIME_ORDER")

    claim = _validate_claim_and_ledger(
        value,
        relative=relative,
        request_rel=request_rel,
        raw=raw,
        request_sha=request_sha,
        identity=identity,
        root=root,
    )
    if status == "PREPARING":
        if (
            value.get("backup_manifest_sha256") is not None
            or value.get("backup_receipt_sha256") is not None
            or value.get("opened_at") is not None
        ):
            raise WatchdogError("TRANSACTION_PREPARING_HAS_BACKUP_STATE")
    else:
        try:
            opened_at = cp.parse_utc(str(value.get("opened_at", "")))
        except cp.ControlPlaneError as exc:
            raise WatchdogError("TRANSACTION_OPEN_TIME_INVALID") from exc
        if opened_at < prepared_at or opened_at >= expires_at:
            raise WatchdogError("TRANSACTION_OPEN_TIME_ORDER")
        _validate_backup_receipt(
            value,
            raw=raw,
            request_sha=request_sha,
            root=root,
        )
    return value | {
        "claim_path": cp.claim_relative_path(identity),
        "source_commit": str(claim["autostart_source_commit"]),
        "transaction_path": relative,
        "transaction_status": status,
    }


def discover(*, root: pathlib.Path = ROOT) -> dict[str, Any]:
    folder = root / "state/transactions"
    if not folder.exists():
        return {
            "has_pending": False,
            "pending_count": 0,
            "transaction_status": "NONE",
        }
    if folder.is_symlink() or not folder.is_dir():
        raise WatchdogError("TRANSACTION_FOLDER_INVALID")
    pending_paths: list[pathlib.Path] = []
    for path in sorted(folder.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise WatchdogError("TRANSACTION_FILE_INVALID")
        try:
            value = cp.read_json(path)
        except cp.ControlPlaneError as exc:
            raise WatchdogError("TRANSACTION_JSON_INVALID") from exc
        status = str(value.get("status", ""))
        if status in PENDING_STATUSES:
            pending_paths.append(path)
        elif status not in TERMINAL_STATUSES:
            raise WatchdogError("TRANSACTION_STATUS_INVALID")
    if not pending_paths:
        return {
            "has_pending": False,
            "pending_count": 0,
            "transaction_status": "NONE",
        }
    if len(pending_paths) != 1:
        raise WatchdogError("MULTIPLE_PENDING_PRODUCTION_TRANSACTIONS")
    result = validate_transaction(pending_paths[0], root=root)
    result["has_pending"] = True
    result["pending_count"] = 1
    return result


def assert_clear(*, root: pathlib.Path = ROOT) -> dict[str, Any]:
    result = discover(root=root)
    if result["has_pending"]:
        raise WatchdogError(
            "PENDING_PRODUCTION_TRANSACTION:" + str(result["transaction_status"])
        )
    return result | {"status": "PASS"}


def _github_outputs(result: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {
        "has_pending": str(bool(result["has_pending"])).lower(),
        "pending_count": result.get("pending_count", 0),
        "transaction_status": result.get("transaction_status", "NONE"),
    }
    if result["has_pending"]:
        values.update(
            {
                "request_path": result["request_path"],
                "request_sha256": result["request_sha256"],
                "run_id": result["run_id"],
                "claim_path": result["claim_path"],
                "source_commit": result["source_commit"],
                "task_id": result["task_id"],
                "transaction_id": result["transaction_id"],
                "transaction_path": result["transaction_path"],
            }
        )
        if result["transaction_status"] in {"OPEN", "ROLLING_BACK"}:
            values["backup_manifest_sha256"] = result["backup_manifest_sha256"]
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("discover", "assert-clear"))
    args = parser.parse_args()
    result = discover() if args.command == "discover" else assert_clear()
    _output(_github_outputs(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
