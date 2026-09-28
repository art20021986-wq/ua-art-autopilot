"""Fail-closed schemas and state transitions for the TASK116 registry."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping


TASK_ID_RE = re.compile(r"^TASK[0-9]{3}(?:-[A-Z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

STATES = {
    "RECEIVED",
    "PLANNING",
    "PACKAGE_READY",
    "SANDBOX_RUNNING",
    "GATE_PENDING",
    "OWNER_APPROVAL_PENDING",
    "PRODUCTION_QUEUED",
    "BACKUP_READY",
    "PRODUCTION_OPEN",
    "VERIFYING",
    "FINISHED",
    "ROLLING_BACK",
    "ROLLED_BACK",
    "BLOCKED",
    "HALTED_P0",
}

TERMINAL_STATES = {"FINISHED", "ROLLED_BACK", "BLOCKED", "HALTED_P0"}

TRANSITIONS = {
    "RECEIVED": {"PLANNING", "BLOCKED", "HALTED_P0"},
    "PLANNING": {"PACKAGE_READY", "BLOCKED", "HALTED_P0"},
    "PACKAGE_READY": {"SANDBOX_RUNNING", "BLOCKED", "HALTED_P0"},
    "SANDBOX_RUNNING": {"GATE_PENDING", "BLOCKED", "HALTED_P0"},
    "GATE_PENDING": {"OWNER_APPROVAL_PENDING", "BLOCKED", "HALTED_P0"},
    "OWNER_APPROVAL_PENDING": {"PRODUCTION_QUEUED", "BLOCKED", "HALTED_P0"},
    "PRODUCTION_QUEUED": {"BACKUP_READY", "BLOCKED", "HALTED_P0"},
    "BACKUP_READY": {"PRODUCTION_OPEN", "BLOCKED", "HALTED_P0"},
    "PRODUCTION_OPEN": {"VERIFYING", "ROLLING_BACK", "HALTED_P0"},
    "VERIFYING": {"FINISHED", "ROLLING_BACK", "HALTED_P0"},
    "ROLLING_BACK": {"ROLLED_BACK", "HALTED_P0"},
    "ROLLED_BACK": set(),
    "FINISHED": set(),
    "BLOCKED": {"PLANNING", "PACKAGE_READY", "SANDBOX_RUNNING"},
    "HALTED_P0": {"PLANNING", "PACKAGE_READY", "SANDBOX_RUNNING", "ROLLING_BACK"},
}


class ContractError(ValueError):
    """Raised when a registry or transition contract is unsafe."""


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key}: required non-empty string")
    return value


def _require_bool(record: Mapping[str, object], key: str) -> bool:
    value = record.get(key)
    if not isinstance(value, bool):
        raise ContractError(f"{key}: required boolean")
    return value


def validate_record(record: Mapping[str, object]) -> dict[str, object]:
    """Validate a canonical registry record and return a plain copy."""

    if not isinstance(record, Mapping):
        raise ContractError("record: required object")

    task_id = _require_text(record, "task_id")
    if not TASK_ID_RE.fullmatch(task_id):
        raise ContractError("task_id: invalid format")

    request_sha256 = _require_text(record, "request_sha256")
    if not SHA256_RE.fullmatch(request_sha256):
        raise ContractError("request_sha256: invalid sha256")

    state = _require_text(record, "state")
    if state not in STATES:
        raise ContractError("state: unsupported")

    production_required = _require_bool(record, "production_required")
    production_allowed = _require_bool(record, "production_allowed")
    gate_b_pass = _require_bool(record, "gate_b_pass")
    owner_approved = _require_bool(record, "owner_approved")
    backup_ready = _require_bool(record, "backup_ready")

    if production_allowed and not production_required:
        raise ContractError("production_allowed without production_required")
    if production_allowed and not (gate_b_pass and owner_approved and backup_ready):
        raise ContractError("production requires Gate B, owner approval and backup")
    if state in {"PRODUCTION_OPEN", "VERIFYING", "FINISHED"} and production_required:
        if not production_allowed:
            raise ContractError("production state entered without authorization")

    resources = record.get("resources")
    if not isinstance(resources, list) or not resources:
        raise ContractError("resources: required non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in resources):
        raise ContractError("resources: invalid item")
    if len(resources) != len(set(resources)):
        raise ContractError("resources: duplicates forbidden")

    return dict(record)


def validate_transition(before: Mapping[str, object], after: Mapping[str, object]) -> None:
    """Reject identity drift and illegal state transitions."""

    old = validate_record(before)
    new = validate_record(after)
    for key in ("task_id", "request_sha256", "production_required"):
        if old[key] != new[key]:
            raise ContractError(f"{key}: immutable identity drift")

    old_state = str(old["state"])
    new_state = str(new["state"])
    if new_state == old_state:
        return
    if new_state not in TRANSITIONS[old_state]:
        raise ContractError(f"illegal transition: {old_state} -> {new_state}")

    if old_state in TERMINAL_STATES and new_state != old_state:
        if old_state not in {"BLOCKED", "HALTED_P0"}:
            raise ContractError("terminal state cannot be reopened")
