#!/usr/bin/env python3
"""Fail-closed intake for new global UA ART autostart launch markers."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import importlib.util
import json
import os
import pathlib
import re
import sys
from typing import Any

AUTOMATION_ROOT = pathlib.Path(__file__).resolve().parent
ROOT = AUTOMATION_ROOT.parent


def _load_trusted_sibling(name: str):
    """Load a pinned automation sibling explicitly, including under Python -I."""
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = AUTOMATION_ROOT / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("AUTOSTART_TRUSTED_MODULE_SPEC:" + name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cp = _load_trusted_sibling("control_plane")
ca = _load_trusted_sibling("critical_adapter")
LAUNCH_SCHEMA = "UA-ART-AUTOSTART-LAUNCH-1"
PRODUCTION_AUTHORIZATION_SCHEMA = "UA-ART-PRODUCTION-AUTHORIZATION-1"
NONCE_RE = re.compile(r"^[A-Za-z0-9._-]{16,128}$")
ALLOWED_KEYS = {
    "action",
    "created_at",
    "expires_at",
    "nonce",
    "mode_epoch",
    "owner_authorized",
    "production_allowed",
    "request_path",
    "request_sha256",
    "schema_version",
    "task_id",
}


class AutostartIntakeError(ValueError):
    """A launch marker failed a mandatory automatic-mode guard."""


def _unresolved_repo_path(
    value: str,
    *,
    root: pathlib.Path,
    label: str,
    must_exist: bool = False,
) -> pathlib.Path:
    """Return the lexical path and reject every symlinked path component."""
    normalized = cp.safe_repo_path(value)
    base = root.resolve(strict=True)
    candidate = base / normalized
    resolved = cp.repo_path(normalized, base)
    if candidate != resolved or candidate.is_symlink():
        raise AutostartIntakeError("AUTOSTART_SYMLINK_PATH:" + label)
    if must_exist and not candidate.is_file():
        raise AutostartIntakeError("AUTOSTART_FILE_MISSING:" + label)
    return candidate


def _write_outputs(values: dict[str, Any]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            text = str(value)
            if "\n" in text or "\r" in text:
                raise AutostartIntakeError("MULTILINE_OUTPUT:" + key)
            handle.write(f"{key}={text}\n")


def _ledger_rel(task_id: str, request_sha256: str) -> str:
    if not cp.TASK_ID_RE.fullmatch(task_id):
        raise AutostartIntakeError("AUTOSTART_LEDGER_TASK_ID_INVALID")
    if not cp.SHA_RE.fullmatch(request_sha256):
        raise AutostartIntakeError("AUTOSTART_LEDGER_REQUEST_SHA_INVALID")
    return f"state/autostart_consumed/{task_id}.{request_sha256}.json"


def _nonce_rel(nonce: str) -> str:
    if not NONCE_RE.fullmatch(nonce):
        raise AutostartIntakeError("AUTOSTART_NONCE_INVALID")
    return f"state/autostart_nonces/{nonce}.json"


def request_authorization_sha256(request: dict[str, Any]) -> str:
    """Hash the exact request while breaking the approval/hash cycle.

    The request pins the approval file SHA.  The approval in turn pins this
    subject hash, which is the canonical request with only that one SHA field
    replaced by a fixed sentinel.  Every executable field remains bound.
    """
    subject = copy.deepcopy(request)
    critical = subject.get("critical")
    if not isinstance(critical, dict) or "owner_approval_sha256" not in critical:
        raise AutostartIntakeError("AUTOSTART_OWNER_APPROVAL_BINDING_REQUIRED")
    critical["owner_approval_sha256"] = "0" * 64
    return cp.sha256_bytes(cp.canonical_json(subject))


def _validate_production_authorization(
    request: dict[str, Any],
    critical: dict[str, Any],
    marker: dict[str, Any],
    mode: dict[str, Any],
    current: dt.datetime,
    *,
    root: pathlib.Path,
) -> dict[str, Any]:
    """Validate the complete immutable Gate B input before consuming a marker."""
    flat = {
        "task_id": request["task_id"],
        "title": request["title"],
        "description": request.get("description", ""),
        "changed_paths": request.get("changed_paths", []),
        "production_required": True,
        "requested_min_class": request.get("requested_min_class"),
        "owner_approval_path": critical.get("owner_approval_path"),
        "owner_approval_sha256": critical.get("owner_approval_sha256"),
        "manifest_path": critical.get("manifest_path"),
        "manifest_sha256": critical.get("manifest_sha256"),
        "gate_b_authorized": critical.get("gate_b_authorized"),
        "allow_crm_vehicle_data": critical.get("allow_crm_vehicle_data", False),
    }
    try:
        critical_request = ca.CriticalRequest.from_mapping(flat)
        owner_path = _unresolved_repo_path(
            critical_request.owner_approval_path,
            root=root,
            label="owner_approval",
            must_exist=True,
        )
        owner_content = owner_path.read_bytes()
        if not critical_request.owner_approval_path.startswith("tasks/approvals/") \
                or not critical_request.owner_approval_path.endswith(".production.json"):
            raise AutostartIntakeError("AUTOSTART_OWNER_APPROVAL_PATH_SCOPE")
        approval = cp.read_json(owner_path)
        expected_keys = {
            "approved_at",
            "authorization_id",
            "authorized_environment",
            "expires_at",
            "gate_a_sha256",
            "launch_nonce",
            "manifest_sha256",
            "mode_epoch",
            "owner",
            "owner_authorized",
            "production_allowed",
            "request_path",
            "request_subject_sha256",
            "schema_version",
            "task_id",
        }
        if set(approval) != expected_keys:
            raise AutostartIntakeError("AUTOSTART_OWNER_APPROVAL_SCHEMA")
        if approval.get("schema_version") != PRODUCTION_AUTHORIZATION_SCHEMA:
            raise AutostartIntakeError("AUTOSTART_OWNER_APPROVAL_SCHEMA")
        if not re.fullmatch(r"prod-auth-[A-Za-z0-9._-]{16,100}", str(approval.get("authorization_id", ""))):
            raise AutostartIntakeError("AUTOSTART_OWNER_AUTHORIZATION_ID")
        if approval.get("task_id") != request["task_id"]:
            raise AutostartIntakeError("AUTOSTART_TASK_SPECIFIC_OWNER_APPROVAL_REQUIRED")
        if approval.get("request_path") != marker.get("request_path"):
            raise AutostartIntakeError("AUTOSTART_OWNER_REQUEST_PATH_BINDING")
        if approval.get("request_subject_sha256") != request_authorization_sha256(request):
            raise AutostartIntakeError("AUTOSTART_OWNER_REQUEST_SUBJECT_BINDING")
        if approval.get("manifest_sha256") != critical_request.manifest_sha256:
            raise AutostartIntakeError("AUTOSTART_OWNER_MANIFEST_BINDING")
        if approval.get("gate_a_sha256") != cp.require_sha(critical.get("gate_a_sha256"), "gate_a"):
            raise AutostartIntakeError("AUTOSTART_OWNER_GATE_A_BINDING")
        if approval.get("mode_epoch") != mode.get("mode_epoch"):
            raise AutostartIntakeError("AUTOSTART_OWNER_MODE_EPOCH_BINDING")
        if approval.get("launch_nonce") != marker.get("nonce"):
            raise AutostartIntakeError("AUTOSTART_OWNER_NONCE_BINDING")
        if approval.get("owner") != "Артём Бровинский / UA ART COMPANY LLC":
            raise AutostartIntakeError("AUTOSTART_OWNER_IDENTITY")
        if approval.get("owner_authorized") is not True:
            raise AutostartIntakeError("AUTOSTART_OWNER_AUTHORIZATION_REQUIRED")
        if approval.get("authorized_environment") != "production":
            raise AutostartIntakeError("AUTOSTART_OWNER_PRODUCTION_SCOPE_REQUIRED")
        if approval.get("production_allowed") is not True:
            raise AutostartIntakeError("AUTOSTART_OWNER_PRODUCTION_DENIED")
        approved_at = cp.parse_utc(str(approval.get("approved_at", "")))
        approval_expires = cp.parse_utc(str(approval.get("expires_at", "")))
        launch_created = cp.parse_utc(str(marker.get("created_at", "")))
        launch_expires = cp.parse_utc(str(marker.get("expires_at", "")))
        if approved_at < cp.parse_utc(str(mode["activated_at"])) or approved_at > launch_created:
            raise AutostartIntakeError("AUTOSTART_OWNER_APPROVAL_TIME_BINDING")
        if approval_expires != launch_expires or current >= approval_expires:
            raise AutostartIntakeError("AUTOSTART_OWNER_APPROVAL_EXPIRED")
        manifest_path = _unresolved_repo_path(
            critical_request.manifest_path,
            root=root,
            label="manifest",
            must_exist=True,
        )
        manifest = cp.read_json(manifest_path)
        gate_rel = cp.safe_repo_path(str(critical.get("gate_a_path", "")))
        gate_path = _unresolved_repo_path(
            gate_rel, root=root, label="gate_a", must_exist=True
        )
        if cp.sha256_file(gate_path) != cp.require_sha(critical.get("gate_a_sha256"), "gate_a"):
            raise AutostartIntakeError("AUTOSTART_GATE_A_SHA_MISMATCH")
        gate_a = cp.read_json(gate_path)
        result = ca.authorize_gate_b(critical_request, owner_content, manifest, gate_a)
        result["approval_path"] = critical_request.owner_approval_path
        result["approval_sha256"] = critical_request.owner_approval_sha256
        result["request_subject_sha256"] = approval["request_subject_sha256"]
        return result
    except AutostartIntakeError:
        raise
    except (OSError, UnicodeDecodeError, cp.ControlPlaneError, ca.CriticalAdapterError) as exc:
        raise AutostartIntakeError("AUTOSTART_PRODUCTION_AUTHORIZATION_INVALID:" + str(exc)) from exc


def _validate_production_recovery_contract(
    execution: dict[str, Any],
    *,
    root: pathlib.Path,
) -> None:
    required = (
        "backup_controller_path",
        "backup_controller_sha256",
        "backup_receipt_path",
        "rollback_controller_path",
        "rollback_controller_sha256",
        "rollback_receipt_path",
    )
    if any(not str(execution.get(key, "")).strip() for key in required):
        raise AutostartIntakeError("AUTOSTART_PRODUCTION_ROLLBACK_CONTRACT_REQUIRED")
    evidence = execution.get("evidence_paths")
    if not isinstance(evidence, list):
        raise AutostartIntakeError("AUTOSTART_RECOVERY_EVIDENCE_REQUIRED")
    receipts: set[str] = set()
    for operation in ("backup", "rollback"):
        controller_rel = cp.safe_repo_path(str(execution[f"{operation}_controller_path"]))
        if not (
            controller_rel.startswith("cloud/")
            or controller_rel.startswith("automation/packages/")
        ) or not controller_rel.endswith(".py"):
            raise AutostartIntakeError(
                f"AUTOSTART_{operation.upper()}_CONTROLLER_SCOPE"
            )
        controller = _unresolved_repo_path(
            controller_rel,
            root=root,
            label=f"{operation}_controller",
            must_exist=True,
        )
        if cp.sha256_file(controller) != cp.require_sha(
            execution.get(f"{operation}_controller_sha256"), f"{operation}_controller"
        ):
            raise AutostartIntakeError(
                f"AUTOSTART_{operation.upper()}_CONTROLLER_SHA_MISMATCH"
            )
        receipt_rel = cp.safe_repo_path(str(execution[f"{operation}_receipt_path"]))
        if not receipt_rel.startswith("state/receipts/") or not receipt_rel.endswith(".json"):
            raise AutostartIntakeError(f"AUTOSTART_{operation.upper()}_RECEIPT_SCOPE")
        if receipt_rel in receipts or receipt_rel == execution.get("receipt_path"):
            raise AutostartIntakeError("AUTOSTART_RECOVERY_RECEIPT_COLLISION")
        receipts.add(receipt_rel)
        if receipt_rel not in evidence:
            raise AutostartIntakeError(
                f"AUTOSTART_{operation.upper()}_RECEIPT_NOT_IN_EVIDENCE"
            )


def validate_launch(
    launch_path: str,
    run_id: str,
    source_commit: str,
    *,
    root: pathlib.Path = ROOT,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    mode = cp.verify_execution_mode(root=root, required_mode="AUTOMATIC")
    launch_rel = cp.safe_repo_path(launch_path)
    if not launch_rel.startswith("tasks/launch/AUTO-") or not launch_rel.endswith(".json"):
        raise AutostartIntakeError("AUTOSTART_LAUNCH_PATH_SCOPE")
    launch_file = _unresolved_repo_path(
        launch_rel, root=root, label="launch", must_exist=True
    )
    marker = cp.read_json(launch_file)
    if set(marker) != ALLOWED_KEYS:
        raise AutostartIntakeError("AUTOSTART_LAUNCH_KEYS_MISMATCH")
    if marker.get("schema_version") != LAUNCH_SCHEMA or marker.get("action") != "RUN_EXACT_TASK":
        raise AutostartIntakeError("AUTOSTART_LAUNCH_SCHEMA_OR_ACTION")
    if marker.get("owner_authorized") is not True:
        raise AutostartIntakeError("AUTOSTART_OWNER_AUTHORIZATION_REQUIRED")
    if marker.get("mode_epoch") != mode.get("mode_epoch"):
        raise AutostartIntakeError("AUTOSTART_MODE_EPOCH_MISMATCH")
    nonce = str(marker.get("nonce", ""))
    if not NONCE_RE.fullmatch(nonce):
        raise AutostartIntakeError("AUTOSTART_NONCE_INVALID")
    if not re.fullmatch(r"[0-9a-f]{40}", str(source_commit)):
        raise AutostartIntakeError("AUTOSTART_SOURCE_COMMIT_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(run_id)):
        raise AutostartIntakeError("AUTOSTART_RUN_ID_INVALID")

    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    created = cp.parse_utc(str(marker.get("created_at", "")))
    expires = cp.parse_utc(str(marker.get("expires_at", "")))
    activated = cp.parse_utc(str(mode["activated_at"]))
    if created < activated:
        raise AutostartIntakeError("AUTOSTART_MARKER_PREDATES_ACTIVATION")
    if created > current + dt.timedelta(minutes=2):
        raise AutostartIntakeError("AUTOSTART_MARKER_FROM_FUTURE")
    if expires <= created or expires - created > dt.timedelta(hours=2):
        raise AutostartIntakeError("AUTOSTART_EXPIRY_RANGE")
    if current >= expires:
        raise AutostartIntakeError("AUTOSTART_MARKER_EXPIRED")

    marker_request_rel = cp.safe_repo_path(str(marker.get("request_path", "")))
    _unresolved_repo_path(
        marker_request_rel, root=root, label="request", must_exist=True
    )
    request_rel, _, request, request_sha = cp.load_request(marker_request_rel, root)
    expected_sha = cp.require_sha(marker.get("request_sha256"), "autostart_request")
    if request_sha != expected_sha:
        raise AutostartIntakeError("AUTOSTART_REQUEST_SHA_MISMATCH")
    if request.get("task_id") != marker.get("task_id"):
        raise AutostartIntakeError("AUTOSTART_TASK_ID_MISMATCH")
    if request.get("control_plane_version") != "TASK107-R2":
        raise AutostartIntakeError("AUTOSTART_CONTROL_PLANE_VERSION")

    execution = request.get("execution")
    if not isinstance(execution, dict):
        raise AutostartIntakeError("AUTOSTART_EXECUTION_OBJECT_REQUIRED")
    production = bool(request.get("production_required", False))
    if bool(execution.get("production_required", False)) != production:
        raise AutostartIntakeError("AUTOSTART_EXECUTION_PRODUCTION_MISMATCH")
    if production:
        if marker.get("production_allowed") is not True or mode.get("automatic_production") is not True:
            raise AutostartIntakeError("AUTOSTART_PRODUCTION_NOT_ALLOWED")
        if cp.classify_request(request) != "CRITICAL":
            raise AutostartIntakeError("AUTOSTART_PRODUCTION_MUST_BE_CRITICAL")
        critical = request.get("critical")
        if not isinstance(critical, dict) or critical.get("gate_b_authorized") is not True:
            raise AutostartIntakeError("AUTOSTART_PRODUCTION_GATE_B_REQUIRED")
        if not request.get("health_checks") or not isinstance(request.get("storage_probe"), dict):
            raise AutostartIntakeError("AUTOSTART_PRODUCTION_HEALTH_STORAGE_REQUIRED")
        _validate_production_recovery_contract(execution, root=root)
        gate_b = _validate_production_authorization(
            request, critical, marker, mode, current, root=root
        )
        if gate_b.get("status") != "GATE_B_AUTHORIZED":
            raise AutostartIntakeError("AUTOSTART_GATE_B_NOT_AUTHORIZED")
    elif marker.get("production_allowed") is not False:
        raise AutostartIntakeError("AUTOSTART_NONPRODUCTION_FLAG_MUST_BE_FALSE")

    receipt_rel = cp.safe_repo_path(str(execution.get("receipt_path", "")))
    if cp.repo_path(receipt_rel, root).exists():
        raise AutostartIntakeError("AUTOSTART_REQUEST_ALREADY_HAS_RECEIPT")
    rollback_receipt_rel = str(execution.get("rollback_receipt_path", "")).strip()
    if rollback_receipt_rel and cp.repo_path(cp.safe_repo_path(rollback_receipt_rel), root).exists():
        raise AutostartIntakeError("AUTOSTART_REQUEST_ALREADY_HAS_ROLLBACK_RECEIPT")

    consumed_dir = root / "state/autostart_consumed"
    if (
        consumed_dir.is_symlink()
        or consumed_dir.resolve(strict=False) != consumed_dir
        or (consumed_dir.exists() and not consumed_dir.is_dir())
    ):
        raise AutostartIntakeError("AUTOSTART_CONSUMED_LEDGER_DIRECTORY_INVALID")
    if consumed_dir.is_dir():
        for existing_path in consumed_dir.glob("*.json"):
            if existing_path.is_symlink() or not existing_path.is_file():
                raise AutostartIntakeError(
                    "AUTOSTART_CONSUMED_LEDGER_FILE_INVALID:" + existing_path.name
                )
            existing = cp.read_json(existing_path)
            if (
                existing.get("request_sha256") == request_sha
                or existing.get("nonce") == nonce
                or existing.get("launch_path") == launch_rel
            ):
                raise AutostartIntakeError("AUTOSTART_REPLAY_BLOCKED:" + existing_path.name)

    ledger_rel = _ledger_rel(str(request["task_id"]), request_sha)
    nonce_rel = _nonce_rel(nonce)
    nonce_reservation = {
        "nonce": nonce,
        "request_sha256": request_sha,
        "run_id": str(run_id),
        "schema_version": cp.AUTOSTART_LEDGER_SCHEMA,
        "source_commit": str(source_commit),
        "status": "RESERVED",
        "task_id": str(request["task_id"]),
    }
    ledger = {
        "consumed_at": current.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "created_at": str(marker["created_at"]),
        "expires_at": str(marker["expires_at"]),
        "launch_path": launch_rel,
        "launch_sha256": cp.sha256_file(launch_file),
        "mode_epoch": str(mode["mode_epoch"]),
        "nonce": nonce,
        "production_allowed": bool(marker["production_allowed"]),
        "production_approval_path": (
            str(request["critical"]["owner_approval_path"]) if production else ""
        ),
        "production_approval_sha256": (
            str(request["critical"]["owner_approval_sha256"]) if production else ""
        ),
        "production_required": production,
        "request_path": request_rel,
        "request_sha256": request_sha,
        "request_subject_sha256": (
            request_authorization_sha256(request) if production else ""
        ),
        "run_id": str(run_id),
        "schema_version": cp.AUTOSTART_LEDGER_SCHEMA,
        "source_commit": str(source_commit),
        "status": "CONSUMED",
        "task_id": str(request["task_id"]),
    }
    return {
        "ledger": ledger,
        "ledger_path": ledger_rel,
        "mode": mode["mode"],
        "nonce_reservation": nonce_reservation,
        "nonce_reservation_path": nonce_rel,
        "production_required": production,
        "request_path": request_rel,
        "request_sha256": request_sha,
        "task_id": str(request["task_id"]),
    }


def consume_launch(
    launch_path: str,
    run_id: str,
    source_commit: str,
    *,
    root: pathlib.Path = ROOT,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    result = validate_launch(launch_path, run_id, source_commit, root=root, now=now)
    nonce_path = _unresolved_repo_path(
        result["nonce_reservation_path"], root=root, label="nonce_reservation"
    )
    cp.atomic_json(nonce_path, result["nonce_reservation"], exclusive=True)
    result["ledger"]["nonce_reservation_path"] = result["nonce_reservation_path"]
    result["ledger"]["nonce_reservation_sha256"] = cp.sha256_file(nonce_path)
    ledger_path = _unresolved_repo_path(
        result["ledger_path"], root=root, label="ledger"
    )
    cp.atomic_json(ledger_path, result["ledger"], exclusive=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("launch_path")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--root", type=pathlib.Path, default=ROOT)
    args = parser.parse_args()
    operation = validate_launch if args.validate_only else consume_launch
    result = operation(
        args.launch_path,
        args.run_id,
        args.source_commit,
        root=args.root.resolve(strict=True),
    )
    _write_outputs({
        "ledger_path": result["ledger_path"],
        "nonce_reservation_path": result["nonce_reservation_path"],
        "production_required": str(result["production_required"]).lower(),
        "request_path": result["request_path"],
        "request_sha256": result["request_sha256"],
        "task_id": result["task_id"],
    })
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
