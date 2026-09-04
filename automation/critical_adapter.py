#!/usr/bin/env python3
"""Strict CRITICAL gate adapter for the UA ART task orchestrator.

This module is deliberately side-effect free. It validates the immutable request,
owner authorization, change manifest, Gate A evidence and final receipts. It has
no network, subprocess, deployment or production-write capability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

CONTRACT_ID = "UA-ART-CRITICAL-ADAPTER-V1.0"
OWNER_MARKER = (
    "УТВЕРЖДАЮ ПРОДОЛЖЕНИЕ UA-ART-FAST-PIPELINE-001 ДО ПОЛНОГО TASK FINISHED"
)
FORBIDDEN_WITHOUT_EXPLICIT_APPROVAL = (
    re.compile(r"(?:^|/)(?:crm\.db|[^/]+\.sqlite3?|[^/]+\.db)$", re.I),
    re.compile(r"(?:^|/)(?:cars?|vehicles?|customers?)(?:/|$)", re.I),
)
SENSITIVE_PATTERNS = (
    re.compile(r"(?:^|/)(?:\.env|secrets?|credentials?|private[_-]?keys?)(?:/|$)", re.I),
    re.compile(r"(?:^|/)(?:dns|cloudflare|wrangler\.jsonc)(?:/|$)", re.I),
)


class CriticalAdapterError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def safe_repo_path(value: str) -> str:
    path = pathlib.PurePosixPath(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise CriticalAdapterError("UNSAFE_REPO_PATH:" + str(value))
    return path.as_posix()


def require_sha(value: str, label: str) -> str:
    text = str(value).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise CriticalAdapterError("INVALID_SHA256:" + label)
    return text


@dataclass(frozen=True)
class CriticalRequest:
    task_id: str
    title: str
    description: str
    changed_paths: tuple[str, ...]
    production_required: bool
    requested_min_class: str
    owner_approval_path: str
    owner_approval_sha256: str
    manifest_path: str
    manifest_sha256: str
    gate_b_authorized: bool
    allow_crm_vehicle_data: bool

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "CriticalRequest":
        task_id = str(raw.get("task_id", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,79}", task_id):
            raise CriticalAdapterError("INVALID_TASK_ID")
        title = str(raw.get("title", "")).strip()
        if not title:
            raise CriticalAdapterError("EMPTY_TITLE")
        description = str(raw.get("description", "")).strip()
        paths_raw = raw.get("changed_paths", [])
        if not isinstance(paths_raw, list) or not paths_raw:
            raise CriticalAdapterError("CHANGED_PATHS_REQUIRED")
        changed_paths = tuple(sorted({safe_repo_path(str(item)) for item in paths_raw}))
        minimum = str(raw.get("requested_min_class", "")).upper()
        if minimum != "CRITICAL":
            raise CriticalAdapterError("CRITICAL_MINIMUM_REQUIRED")
        return cls(
            task_id=task_id,
            title=title,
            description=description,
            changed_paths=changed_paths,
            production_required=bool(raw.get("production_required", False)),
            requested_min_class=minimum,
            owner_approval_path=safe_repo_path(str(raw.get("owner_approval_path", ""))),
            owner_approval_sha256=require_sha(
                str(raw.get("owner_approval_sha256", "")), "owner_approval"
            ),
            manifest_path=safe_repo_path(str(raw.get("manifest_path", ""))),
            manifest_sha256=require_sha(
                str(raw.get("manifest_sha256", "")), "manifest"
            ),
            gate_b_authorized=bool(raw.get("gate_b_authorized", False)),
            allow_crm_vehicle_data=bool(raw.get("allow_crm_vehicle_data", False)),
        )


def validate_owner_approval(request: CriticalRequest, content: bytes) -> dict[str, Any]:
    if sha256_bytes(content) != request.owner_approval_sha256:
        raise CriticalAdapterError("OWNER_APPROVAL_SHA_MISMATCH")
    text = content.decode("utf-8")
    try:
        structured = json.loads(text)
    except json.JSONDecodeError:
        structured = None
    if isinstance(structured, dict):
        if structured.get("schema_version") != "UA-ART-PRODUCTION-AUTHORIZATION-1":
            raise CriticalAdapterError("OWNER_APPROVAL_SCHEMA")
        if structured.get("task_id") != request.task_id:
            raise CriticalAdapterError("OWNER_APPROVAL_TASK_ID")
        if structured.get("manifest_sha256") != request.manifest_sha256:
            raise CriticalAdapterError("OWNER_APPROVAL_MANIFEST_SHA")
        if structured.get("authorized_environment") != "production":
            raise CriticalAdapterError("OWNER_APPROVAL_ENVIRONMENT")
        if structured.get("owner_authorized") is not True \
                or structured.get("production_allowed") is not True:
            raise CriticalAdapterError("OWNER_APPROVAL_PRODUCTION_DENIED")
    else:
        # Legacy MANUAL requests remain readable.  Automatic intake rejects
        # this free-form format and accepts only the structured schema above.
        if OWNER_MARKER not in text:
            raise CriticalAdapterError("OWNER_APPROVAL_MARKER_MISSING")
        if "CRITICAL" not in text or "rollback" not in text:
            raise CriticalAdapterError("OWNER_APPROVAL_SCOPE_INCOMPLETE")
    return {
        "status": "PASS",
        "path": request.owner_approval_path,
        "sha256": request.owner_approval_sha256,
    }


def _matches(path: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(pattern.search(path) for pattern in patterns)


def validate_manifest(
    request: CriticalRequest,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if sha256_json(manifest) != request.manifest_sha256:
        raise CriticalAdapterError("MANIFEST_SHA_MISMATCH")
    if manifest.get("contract_id") != CONTRACT_ID:
        raise CriticalAdapterError("MANIFEST_CONTRACT")
    if manifest.get("task_id") != request.task_id:
        raise CriticalAdapterError("MANIFEST_TASK_ID")
    if str(manifest.get("task_class", "")).upper() != "CRITICAL":
        raise CriticalAdapterError("MANIFEST_CLASS")
    operations = manifest.get("operations")
    if not isinstance(operations, list) or not operations:
        raise CriticalAdapterError("MANIFEST_OPERATIONS_REQUIRED")
    normalized_paths = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise CriticalAdapterError("OPERATION_NOT_OBJECT:%d" % index)
        action = str(operation.get("action", "")).lower()
        if action not in {"create", "replace", "delete", "noop"}:
            raise CriticalAdapterError("OPERATION_ACTION:%d" % index)
        path = safe_repo_path(str(operation.get("path", "")))
        normalized_paths.append(path)
        if _matches(path, SENSITIVE_PATTERNS):
            raise CriticalAdapterError("SENSITIVE_SCOPE_FORBIDDEN:" + path)
        if _matches(path, FORBIDDEN_WITHOUT_EXPLICIT_APPROVAL):
            if not request.allow_crm_vehicle_data:
                raise CriticalAdapterError("CRM_VEHICLE_SCOPE_NOT_AUTHORIZED:" + path)
            if not bool(manifest.get("explicit_crm_vehicle_approval", False)):
                raise CriticalAdapterError("CRM_VEHICLE_MANIFEST_APPROVAL_MISSING")
        if action != "noop":
            before = operation.get("expected_before_sha256")
            after = operation.get("expected_after_sha256")
            if before is not None:
                require_sha(str(before), "operation_before_%d" % index)
            if action in {"create", "replace"}:
                require_sha(str(after or ""), "operation_after_%d" % index)
    if sorted(set(normalized_paths)) != sorted(set(request.changed_paths)):
        raise CriticalAdapterError("MANIFEST_CHANGED_PATHS_MISMATCH")
    protected = manifest.get("protected_paths")
    if not isinstance(protected, list) or not protected:
        raise CriticalAdapterError("PROTECTED_PATHS_REQUIRED")
    protected_paths = tuple(sorted({safe_repo_path(str(item)) for item in protected}))
    if any(path in normalized_paths for path in protected_paths):
        raise CriticalAdapterError("PROTECTED_TARGET_OVERLAP")
    if manifest.get("backup_required") is not True:
        raise CriticalAdapterError("BACKUP_REQUIRED")
    if manifest.get("rollback_required") is not True:
        raise CriticalAdapterError("ROLLBACK_REQUIRED")
    if manifest.get("live_verify_required") is not True:
        raise CriticalAdapterError("LIVE_VERIFY_REQUIRED")
    return {
        "status": "PASS",
        "task_id": request.task_id,
        "operation_count": len(operations),
        "protected_count": len(protected_paths),
        "manifest_sha256": request.manifest_sha256,
    }


def validate_gate_a(
    request: CriticalRequest,
    gate_a: Mapping[str, Any],
) -> dict[str, Any]:
    if gate_a.get("contract_id") != CONTRACT_ID:
        raise CriticalAdapterError("GATE_A_CONTRACT")
    if gate_a.get("task_id") != request.task_id:
        raise CriticalAdapterError("GATE_A_TASK_ID")
    if gate_a.get("status") != "PASS":
        raise CriticalAdapterError("GATE_A_NOT_PASS")
    if gate_a.get("production_write") is not False:
        raise CriticalAdapterError("GATE_A_PRODUCTION_WRITE")
    if gate_a.get("tests") != "PASS":
        raise CriticalAdapterError("GATE_A_TESTS")
    if int(gate_a.get("unexpected_changes", -1)) != 0:
        raise CriticalAdapterError("GATE_A_UNEXPECTED_CHANGES")
    if gate_a.get("backup_plan_ready") is not True:
        raise CriticalAdapterError("GATE_A_BACKUP_PLAN")
    if gate_a.get("rollback_plan_ready") is not True:
        raise CriticalAdapterError("GATE_A_ROLLBACK_PLAN")
    if gate_a.get("manifest_sha256") != request.manifest_sha256:
        raise CriticalAdapterError("GATE_A_MANIFEST_SHA")
    protected = gate_a.get("protected_snapshot")
    if not isinstance(protected, dict) or not protected:
        raise CriticalAdapterError("GATE_A_PROTECTED_SNAPSHOT")
    return {
        "status": "PASS",
        "task_id": request.task_id,
        "manifest_sha256": request.manifest_sha256,
        "protected_count": len(protected),
    }


def authorize_gate_b(
    request: CriticalRequest,
    owner_content: bytes,
    manifest: Mapping[str, Any],
    gate_a: Mapping[str, Any],
) -> dict[str, Any]:
    if not request.production_required:
        raise CriticalAdapterError("GATE_B_REQUIRES_PRODUCTION_TASK")
    if not request.gate_b_authorized:
        raise CriticalAdapterError("GATE_B_OWNER_AUTHORIZATION_MISSING")
    owner = validate_owner_approval(request, owner_content)
    manifest_result = validate_manifest(request, manifest)
    gate_a_result = validate_gate_a(request, gate_a)
    return {
        "contract_id": CONTRACT_ID,
        "task_id": request.task_id,
        "status": "GATE_B_AUTHORIZED",
        "production_write": False,
        "owner_approval_sha256": owner["sha256"],
        "manifest_sha256": manifest_result["manifest_sha256"],
        "gate_a_manifest_sha256": gate_a_result["manifest_sha256"],
        "rollback_required": True,
        "live_verify_required": True,
    }


def validate_final_receipt(
    request: CriticalRequest,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "contract_id",
        "task_id",
        "status",
        "task_class",
        "target_environment",
        "tests",
        "backup",
        "production",
        "live_verify",
        "rollback",
        "unexpected_changes",
        "protected_files_unchanged",
        "crm_unchanged",
        "manifest_sha256",
    }
    missing = sorted(required - set(receipt))
    if missing:
        raise CriticalAdapterError("FINAL_MISSING:" + ",".join(missing))
    if receipt["contract_id"] != CONTRACT_ID:
        raise CriticalAdapterError("FINAL_CONTRACT")
    if receipt["task_id"] != request.task_id:
        raise CriticalAdapterError("FINAL_TASK_ID")
    if receipt["status"] != "FINISHED":
        raise CriticalAdapterError("FINAL_STATUS")
    if str(receipt["task_class"]).upper() != "CRITICAL":
        raise CriticalAdapterError("FINAL_CLASS")
    if str(receipt["target_environment"]).lower() != "production":
        raise CriticalAdapterError("FINAL_ENVIRONMENT")
    for field in ("tests", "production", "live_verify", "rollback"):
        if receipt[field] != "PASS":
            raise CriticalAdapterError("FINAL_" + field.upper())
    if not str(receipt["backup"]).strip():
        raise CriticalAdapterError("FINAL_BACKUP")
    if int(receipt["unexpected_changes"]) != 0:
        raise CriticalAdapterError("FINAL_UNEXPECTED_CHANGES")
    if receipt["protected_files_unchanged"] is not True:
        raise CriticalAdapterError("FINAL_PROTECTED_DRIFT")
    if receipt["crm_unchanged"] is not True:
        raise CriticalAdapterError("FINAL_CRM_DRIFT")
    if receipt["manifest_sha256"] != request.manifest_sha256:
        raise CriticalAdapterError("FINAL_MANIFEST_SHA")
    return dict(receipt)


def _load_json(path: str) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _load_bytes(path: str) -> bytes:
    return pathlib.Path(path).read_bytes()


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def self_test() -> None:
    owner = (OWNER_MARKER + "\nCRITICAL\nrollback\n").encode()
    manifest = {
        "contract_id": CONTRACT_ID,
        "task_id": "T-CRIT",
        "task_class": "CRITICAL",
        "operations": [{
            "action": "create",
            "path": "video/task105-critical-canary.txt",
            "expected_before_sha256": None,
            "expected_after_sha256": "a" * 64,
        }],
        "protected_paths": ["crm.db", "video/index.html"],
        "backup_required": True,
        "rollback_required": True,
        "live_verify_required": True,
    }
    raw = {
        "task_id": "T-CRIT",
        "title": "Critical adapter canary",
        "description": "deployment architecture",
        "changed_paths": ["video/task105-critical-canary.txt"],
        "production_required": True,
        "requested_min_class": "CRITICAL",
        "owner_approval_path": "tasks/approval.md",
        "owner_approval_sha256": sha256_bytes(owner),
        "manifest_path": "tasks/manifest.json",
        "manifest_sha256": sha256_json(manifest),
        "gate_b_authorized": True,
        "allow_crm_vehicle_data": False,
    }
    request = CriticalRequest.from_mapping(raw)
    gate_a = {
        "contract_id": CONTRACT_ID,
        "task_id": request.task_id,
        "status": "PASS",
        "production_write": False,
        "tests": "PASS",
        "unexpected_changes": 0,
        "backup_plan_ready": True,
        "rollback_plan_ready": True,
        "manifest_sha256": request.manifest_sha256,
        "protected_snapshot": {"crm.db": {"sha256": "b" * 64}},
    }
    result = authorize_gate_b(request, owner, manifest, gate_a)
    assert result["status"] == "GATE_B_AUTHORIZED"
    print("UAART_CRITICAL_ADAPTER_SELF_TEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("request")
    preflight.add_argument("owner")
    preflight.add_argument("manifest")
    gate_b = sub.add_parser("gate-b")
    gate_b.add_argument("request")
    gate_b.add_argument("owner")
    gate_b.add_argument("manifest")
    gate_b.add_argument("gate_a")
    final = sub.add_parser("validate-final")
    final.add_argument("request")
    final.add_argument("receipt")
    sub.add_parser("self-test")
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return
    request_raw = _load_json(args.request)
    request = CriticalRequest.from_mapping(request_raw)
    if args.command == "preflight":
        owner = validate_owner_approval(request, _load_bytes(args.owner))
        manifest = validate_manifest(request, _load_json(args.manifest))
        _dump({"contract_id": CONTRACT_ID, "status": "PASS", "owner": owner, "manifest": manifest})
    elif args.command == "gate-b":
        _dump(authorize_gate_b(
            request,
            _load_bytes(args.owner),
            _load_json(args.manifest),
            _load_json(args.gate_a),
        ))
    else:
        _dump(validate_final_receipt(request, _load_json(args.receipt)))


if __name__ == "__main__":
    main()
