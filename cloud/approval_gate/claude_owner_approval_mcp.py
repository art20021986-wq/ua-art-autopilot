#!/usr/bin/env python3
"""
claude_owner_approval_mcp.py

DESIGN / REFERENCE ONLY. NOT TO BE RUN OR INSTALLED IN TASK_010.

This module sketches the future minimal remote MCP connector that would
let the owner approve/reject release candidates directly from the
ordinary Claude Chat window, WITHOUT giving Claude Chat any ability to
supply arbitrary shell commands, file paths, URLs, file bytes, or code.

Exposed tool surface (and nothing else):

  - get_pending_release()
  - approve_release(task_id, manifest_sha256, owner_confirmation)
  - reject_release(task_id, manifest_sha256, reason)

All three tools operate exclusively on server-side state (the release
manifest store already produced by the Claude Autopilot Actions job).
None of them accept a command, path, URL, or file content parameter.

This file contains NO secrets. Any real secret (owner API key, OAuth
client secret, signing key) must be supplied at deploy time via an
environment variable / secret manager reference, never hardcoded, and
is represented here only as a named placeholder.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import time
import uuid
from typing import Literal

# ---------------------------------------------------------------------------
# Placeholder configuration references (values are never hardcoded here).
# ---------------------------------------------------------------------------
OWNER_SHARED_SECRET_ENV_VAR = "MCP_OWNER_APPROVAL_SECRET"  # set out-of-band
OAUTH_CLIENT_ID_ENV_VAR = "MCP_OAUTH_CLIENT_ID"             # set out-of-band
APPROVAL_TTL_SECONDS = 15 * 60  # approval requests expire quickly


class McpAuthError(Exception):
    pass


class McpValidationError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class PendingRelease:
    task_id: str
    manifest_sha256: str
    file_count: int
    file_summary: tuple[str, ...]
    target_mode: str
    risk_level: str
    requires_gate_a: bool
    requires_gate_b: bool
    created_at_utc: str


@dataclasses.dataclass(frozen=True)
class ApprovalRecord:
    task_id: str
    manifest_sha256: str
    gate: Literal["A", "B"]
    approved: bool
    approved_at_utc: str
    expires_at_utc: str
    owner_phrase_hash: str
    nonce: str  # replay-resistance token, single use


class ReleaseStore:
    """Abstract interface to the server-side release manifest store.

    A real implementation would read/write the same manifest files that
    `pythonanywhere_approval_gate.py` consumes, guarded by file locking
    and append-only audit logging. No implementation is provided here;
    this class only documents the required contract.
    """

    def get_current_pending(self) -> PendingRelease | None:
        raise NotImplementedError("Server-side store required; not implemented in reference.")

    def record_gate_decision(self, record: ApprovalRecord) -> None:
        raise NotImplementedError("Server-side store required; not implemented in reference.")

    def has_used_nonce(self, nonce: str) -> bool:
        raise NotImplementedError("Server-side store required; not implemented in reference.")


def _require_owner_authenticated(caller_token: str) -> None:
    """Reference authentication check. Real deployment must use OAuth
    with owner-only scope, or, at minimum, a per-session server-issued
    token compared with constant-time comparison against a value loaded
    from a secret manager (never a literal in source)."""
    expected = os.environ.get(OWNER_SHARED_SECRET_ENV_VAR)
    if not expected:
        raise McpAuthError("Server not configured with owner secret; refusing all calls.")
    if not caller_token or not _constant_time_eq(caller_token, expected):
        raise McpAuthError("Owner authentication failed.")


def _constant_time_eq(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode("utf-8"), b.encode("utf-8")):
        result |= x ^ y
    return result == 0


# ---------------------------------------------------------------------------
# Tool 1: get_pending_release — read-only
# ---------------------------------------------------------------------------
def get_pending_release(caller_token: str, store: ReleaseStore) -> dict:
    _require_owner_authenticated(caller_token)
    pending = store.get_current_pending()
    if pending is None:
        return {"pending": False}
    return {
        "pending": True,
        "task_id": pending.task_id,
        "manifest_sha256": pending.manifest_sha256,
        "file_count": pending.file_count,
        "file_summary": list(pending.file_summary),
        "target_mode": pending.target_mode,
        "risk_level": pending.risk_level,
        "requires_gate_a": pending.requires_gate_a,
        "requires_gate_b": pending.requires_gate_b,
        "created_at_utc": pending.created_at_utc,
    }


# ---------------------------------------------------------------------------
# Tool 2: approve_release — narrow write, exact-manifest only
# ---------------------------------------------------------------------------
def approve_release(
    caller_token: str,
    store: ReleaseStore,
    task_id: str,
    manifest_sha256: str,
    owner_confirmation: str,
    gate: Literal["A", "B"],
) -> dict:
    """Approves exactly one gate for exactly one manifest.

    Parameters are strictly limited to identifiers and a confirmation
    phrase. There is no path, URL, command, or file-content parameter.
    The server, not the caller, decides what action the manifest allows;
    this tool only records an approval decision bound to the hash.
    """
    _require_owner_authenticated(caller_token)

    if len(manifest_sha256) != 64 or any(c not in "0123456789abcdef" for c in manifest_sha256.lower()):
        raise McpValidationError("manifest_sha256 must be a 64-char hex string.")
    if not task_id or "/" in task_id or ".." in task_id:
        raise McpValidationError("task_id must be a plain identifier.")
    if gate not in ("A", "B"):
        raise McpValidationError("gate must be 'A' or 'B'.")

    pending = store.get_current_pending()
    if pending is None:
        raise McpValidationError("No pending release to approve.")
    if pending.task_id != task_id or pending.manifest_sha256 != manifest_sha256:
        raise McpValidationError(
            "Approval target does not match current pending manifest exactly. Refused."
        )

    required_phrase = (
        f"APPROVE_RUN {task_id.upper()} MANIFEST_SHA256={manifest_sha256}"
        if gate == "A"
        else f"APPROVE_PRODUCTION {task_id.upper()} MANIFEST_SHA256={manifest_sha256}"
    )
    if owner_confirmation.strip() != required_phrase:
        raise McpValidationError("Owner confirmation phrase does not match required exact phrase.")

    nonce = uuid.uuid4().hex
    if store.has_used_nonce(nonce):  # pragma: no cover - astronomically unlikely
        raise McpValidationError("Nonce collision detected; refusing for safety.")

    now = time.time()
    record = ApprovalRecord(
        task_id=task_id,
        manifest_sha256=manifest_sha256,
        gate=gate,
        approved=True,
        approved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        expires_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + APPROVAL_TTL_SECONDS)),
        owner_phrase_hash=hashlib.sha256(required_phrase.encode("utf-8")).hexdigest(),
        nonce=nonce,
    )
    store.record_gate_decision(record)
    return {"status": "APPROVED", "gate": gate, "expires_at_utc": record.expires_at_utc}


# ---------------------------------------------------------------------------
# Tool 3: reject_release — narrow write, exact-manifest only
# ---------------------------------------------------------------------------
def reject_release(
    caller_token: str,
    store: ReleaseStore,
    task_id: str,
    manifest_sha256: str,
    reason: str,
) -> dict:
    _require_owner_authenticated(caller_token)
    if len(manifest_sha256) != 64:
        raise McpValidationError("manifest_sha256 must be 64 hex chars.")
    if not reason or len(reason) > 500:
        raise McpValidationError("reason required, max 500 chars.")

    pending = store.get_current_pending()
    if pending is None or pending.task_id != task_id or pending.manifest_sha256 != manifest_sha256:
        raise McpValidationError("Rejection target does not match current pending manifest.")

    now = time.time()
    record = ApprovalRecord(
        task_id=task_id,
        manifest_sha256=manifest_sha256,
        gate="A",  # rejection is recorded against the pending gate context by the store
        approved=False,
        approved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        expires_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        owner_phrase_hash=hashlib.sha256(reason.encode("utf-8")).hexdigest(),
        nonce=uuid.uuid4().hex,
    )
    store.record_gate_decision(record)
    return {"status": "REJECTED"}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(
        "This module is a design reference for TASK_010 and must not be run "
        "or deployed as an active MCP server in this task."
    )
