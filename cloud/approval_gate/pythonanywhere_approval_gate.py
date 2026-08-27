#!/usr/bin/env python3
"""
pythonanywhere_approval_gate.py

Trusted execution gate design/reference implementation for TASK_010.

STATUS: DESIGN / NOT DEPLOYED / NOT EXECUTED IN THIS TASK.

Python 3.10, standard library only. Default-deny. No eval/exec/dynamic
import. No arbitrary shell command derived from approval input. This
module intentionally does not perform any network, PythonAnywhere API,
or production I/O when imported; the __main__ guard only demonstrates
an offline self-check against a manifest file supplied by the caller.

This file must never be run automatically as part of TASK_010. It is a
reference for the future trusted gate that would run under a
separately provisioned, owner-controlled PythonAnywhere account.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Hardcoded allowlists (must never be derived from manifest content, chat
# input, or environment variables supplied by an untrusted party).
# ---------------------------------------------------------------------------

ALLOWED_SOURCE_ROOT = Path("/home/Carix/autopilot_inbox/cloud/")

ALLOWED_TARGET_ROOTS = (
    Path("/home/Carix/autopilot_inbox/sandbox/"),
    Path("/home/Carix/autopilot_inbox/approved_runs/"),
    # Production roots are intentionally NOT listed here. Gate B targets
    # would require a separate, explicitly reviewed allowlist entry added
    # by the owner/admin out-of-band, never by this file alone.
)

ALLOWED_COMMAND_IDS = {
    "NOOP": {"risk": "LOW", "gate": "A"},
    "RUN_SANDBOX_CHECK_V1": {"risk": "LOW", "gate": "A"},
    "COPY_TO_QUARANTINE_V1": {"risk": "LOW", "gate": "A"},
    # CRITICAL command ids exist only conceptually here; they must never
    # execute without a verified, distinct Gate B record.
    "PRODUCTION_PUBLISH_V1": {"risk": "CRITICAL", "gate": "B"},
    "CRM_WRITE_V1": {"risk": "CRITICAL", "gate": "B"},
    "WSGI_RELOAD_V1": {"risk": "CRITICAL", "gate": "B"},
    "DELETE_V1": {"risk": "CRITICAL", "gate": "B"},
    "MASS_REGEN_V1": {"risk": "CRITICAL", "gate": "B"},
}

CPU_QUOTA_DEFER_THRESHOLD_PERCENT = 85

RECEIPT_DIR = Path("/home/Carix/autopilot_inbox/receipts/")
BACKUP_DIR = Path("/home/Carix/autopilot_inbox/backups/")


class GateDenied(Exception):
    """Raised for any default-deny outcome. Never caught silently."""


@dataclasses.dataclass(frozen=True)
class FileEntry:
    path: str
    sha256: str
    size_bytes: int


@dataclasses.dataclass(frozen=True)
class Manifest:
    schema_version: str
    task_id: str
    created_at_utc: str
    source_commit_sha: str
    github_actions_run_id: str
    github_actions_run_url: str
    claude_authored: bool
    files: tuple[FileEntry, ...]
    target_mode: str
    allowed_action: dict[str, Any]
    requires_gate_a: bool
    requires_gate_b: bool
    backup_required: bool
    rollback_plan: str
    visual_check_required: bool
    risk_level: str
    gate_a: dict[str, Any] | None
    gate_b: dict[str, Any] | None
    manifest_sha256: str
    raw: dict[str, Any]


def _canonical_bytes(obj_without_hash: dict[str, Any]) -> bytes:
    return json.dumps(
        obj_without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def load_manifest(manifest_path: Path) -> Manifest:
    if manifest_path.is_symlink():
        raise GateDenied("Manifest path must not be a symlink.")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_top = {
        "schema_version", "task_id", "created_at_utc", "source_commit_sha",
        "github_actions_run_id", "github_actions_run_url", "claude_authored",
        "files", "target_mode", "allowed_action", "requires_gate_a",
        "requires_gate_b", "backup_required", "rollback_plan",
        "visual_check_required", "risk_level", "manifest_sha256",
    }
    missing = required_top - set(raw.keys())
    if missing:
        raise GateDenied(f"Manifest missing required fields: {sorted(missing)}")

    claimed_hash = raw["manifest_sha256"]
    body = dict(raw)
    del body["manifest_sha256"]
    recomputed = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    if recomputed != claimed_hash:
        raise GateDenied(
            "Manifest hash mismatch: recomputed does not match claimed manifest_sha256. "
            "Treat as tampered or stale. Denying by default."
        )

    files = tuple(
        FileEntry(path=f["path"], sha256=f["sha256"], size_bytes=int(f["size_bytes"]))
        for f in raw["files"]
    )

    return Manifest(
        schema_version=raw["schema_version"],
        task_id=raw["task_id"],
        created_at_utc=raw["created_at_utc"],
        source_commit_sha=raw["source_commit_sha"],
        github_actions_run_id=raw["github_actions_run_id"],
        github_actions_run_url=raw["github_actions_run_url"],
        claude_authored=bool(raw["claude_authored"]),
        files=files,
        target_mode=raw["target_mode"],
        allowed_action=raw["allowed_action"],
        requires_gate_a=bool(raw["requires_gate_a"]),
        requires_gate_b=bool(raw["requires_gate_b"]),
        backup_required=bool(raw["backup_required"]),
        rollback_plan=raw["rollback_plan"],
        visual_check_required=bool(raw["visual_check_required"]),
        risk_level=raw["risk_level"],
        gate_a=raw.get("gate_a"),
        gate_b=raw.get("gate_b"),
        manifest_sha256=claimed_hash,
        raw=raw,
    )


def _resolve_strict(path: Path) -> Path:
    if path.is_symlink():
        raise GateDenied(f"Symlink refused: {path}")
    resolved = path.resolve(strict=False)
    if ".." in path.parts:
        raise GateDenied(f"Path traversal token refused: {path}")
    return resolved


def verify_source_files(manifest: Manifest) -> None:
    if not manifest.claude_authored:
        raise GateDenied("Manifest not marked claude_authored=true. Denying.")
    if not manifest.source_commit_sha or not manifest.github_actions_run_id:
        raise GateDenied("Missing provenance evidence (commit sha / actions run id).")

    for entry in manifest.files:
        rel = entry.path
        if not rel.startswith("cloud/"):
            raise GateDenied(f"File outside cloud/: {rel}")
        full = ALLOWED_SOURCE_ROOT / rel[len("cloud/") :]
        resolved = _resolve_strict(full)
        if not str(resolved).startswith(str(ALLOWED_SOURCE_ROOT.resolve())):
            raise GateDenied(f"Source file escapes allowed source root: {rel}")
        if not resolved.exists():
            raise GateDenied(f"Source file missing on disk: {rel}")
        actual_bytes = resolved.read_bytes()
        actual_hash = hashlib.sha256(actual_bytes).hexdigest()
        if actual_hash != entry.sha256:
            raise GateDenied(
                f"SHA-256 mismatch for {rel}: manifest={entry.sha256} actual={actual_hash}. "
                "Bytes changed after manifest creation. Approval invalid."
            )
        if len(actual_bytes) != entry.size_bytes:
            raise GateDenied(f"Size mismatch for {rel}.")


def verify_targets(manifest: Manifest) -> None:
    targets = manifest.allowed_action.get("target_paths", [])
    if not targets:
        return
    for t in targets:
        target_path = Path(t)
        if target_path.is_symlink():
            raise GateDenied(f"Target is a symlink, refused: {t}")
        if ".." in target_path.parts:
            raise GateDenied(f"Target path traversal refused: {t}")
        if not any(
            str(target_path.resolve(strict=False)).startswith(str(root.resolve(strict=False)))
            for root in ALLOWED_TARGET_ROOTS
        ):
            raise GateDenied(f"Target path outside hardcoded allowlist roots: {t}")


def verify_command_id(manifest: Manifest) -> dict[str, str]:
    command_id = manifest.allowed_action.get("command_id")
    if command_id not in ALLOWED_COMMAND_IDS:
        raise GateDenied(f"Unknown/disallowed command_id: {command_id}")
    return ALLOWED_COMMAND_IDS[command_id]


def verify_gate(manifest: Manifest, gate: str) -> None:
    """gate is 'A' or 'B'. Missing evidence must NEVER be treated as PASS."""
    record = manifest.gate_a if gate == "A" else manifest.gate_b
    if record is None:
        raise GateDenied(f"Gate {gate} approval record absent. Default deny.")
    if not record.get("approved") is True:
        raise GateDenied(f"Gate {gate} approval record present but not approved=true.")
    expires_at = record.get("expires_at_utc")
    if not expires_at:
        raise GateDenied(f"Gate {gate} approval has no expiry. Default deny.")
    if time.time() > _parse_iso_epoch(expires_at):
        raise GateDenied(f"Gate {gate} approval expired. Default deny (stale approval).")
    if not record.get("owner_phrase_hash"):
        raise GateDenied(f"Gate {gate} approval missing owner_phrase_hash evidence.")


def _parse_iso_epoch(iso_str: str) -> float:
    import datetime

    dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.timestamp()


def check_cpu_quota_and_maybe_defer() -> None:
    """Best-effort CPU quota check. On PythonAnywhere the quota status is
    exposed via account API in real deployments; here we only check a
    conservative local proxy (load average) and defer heavy jobs, never
    treating an unreadable quota as green light for CRITICAL work."""
    try:
        load1, _load5, _load15 = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        approx_percent = min(100.0, (load1 / cpu_count) * 100.0)
        if approx_percent >= CPU_QUOTA_DEFER_THRESHOLD_PERCENT:
            raise GateDenied(
                f"CPU load proxy {approx_percent:.1f}% >= "
                f"{CPU_QUOTA_DEFER_THRESHOLD_PERCENT}% threshold; deferring heavy job."
            )
    except (OSError, AttributeError):
        # Unreadable quota must never be treated as PASS for CRITICAL jobs.
        pass


def create_backup_manifest(target_paths: list[str], run_id: str) -> Path | None:
    existing_targets = [Path(t) for t in target_paths if Path(t).exists()]
    if not existing_targets:
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_run_dir = BACKUP_DIR / run_id
    backup_run_dir.mkdir(parents=True, exist_ok=False)
    entries = []
    for p in existing_targets:
        dest = backup_run_dir / p.name
        shutil.copy2(p, dest)
        entries.append({"original": str(p), "backup": str(dest), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest_path = backup_run_dir / "backup_manifest.json"
    manifest_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return manifest_path


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{uuid.uuid4().hex}")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


def write_receipt(manifest: Manifest, gate: str, outcome: str, details: dict[str, Any]) -> Path:
    run_id = f"{manifest.task_id}_{manifest.manifest_sha256[:12]}_{gate}_{uuid.uuid4().hex[:8]}"
    receipt = {
        "task_id": manifest.task_id,
        "manifest_sha256": manifest.manifest_sha256,
        "gate": gate,
        "outcome": outcome,
        "details": details,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    receipt_path = RECEIPT_DIR / f"{run_id}.json"
    _atomic_write_json(receipt_path, receipt)
    return receipt_path


def run_gate_a(manifest_path: Path) -> Path:
    """Executes ONLY a SAFE/SANDBOX action after full verification.
    CRITICAL actions are hard-stopped here regardless of any Gate A record.
    """
    manifest = load_manifest(manifest_path)
    verify_source_files(manifest)
    verify_targets(manifest)
    cmd_meta = verify_command_id(manifest)
    if cmd_meta["gate"] != "A" or cmd_meta["risk"] == "CRITICAL":
        raise GateDenied(
            "Requested command_id requires Gate B; Gate A execution path refuses CRITICAL actions."
        )
    if manifest.target_mode != "SANDBOX_ONLY" and manifest.risk_level not in ("LOW", "MEDIUM"):
        raise GateDenied("Gate A refuses non-sandbox, elevated-risk target_mode.")
    verify_gate(manifest, "A")
    check_cpu_quota_and_maybe_defer()

    backup_path = None
    if manifest.backup_required:
        backup_path = create_backup_manifest(
            manifest.allowed_action.get("target_paths", []), manifest.manifest_sha256[:12]
        )

    try:
        # NOTE: Actual safe/sandbox action execution is intentionally NOT
        # implemented here. This reference only reaches the point of
        # "all checks passed"; a real deployment would dispatch to a
        # narrow, hardcoded, non-shell Python function keyed by
        # command_id, never a dynamically constructed command string.
        result = {"status": "ALL_CHECKS_PASSED_NO_ACTION_TAKEN_IN_THIS_REFERENCE"}
    except Exception as exc:  # pragma: no cover - defensive rollback path
        if backup_path is not None:
            _rollback_from_backup(backup_path)
        raise GateDenied(f"Safe action failed, rollback attempted: {exc}") from exc

    return write_receipt(manifest, "A", "EXECUTED", {"backup_path": str(backup_path) if backup_path else None, "result": result})


def run_gate_b(manifest_path: Path) -> Path:
    """CRITICAL production path. Requires a DISTINCT Gate B record in
    addition to (not instead of) any Gate A record."""
    manifest = load_manifest(manifest_path)
    verify_source_files(manifest)
    verify_targets(manifest)
    cmd_meta = verify_command_id(manifest)
    if cmd_meta["gate"] != "B":
        raise GateDenied("This command_id is not a Gate B (CRITICAL) action.")
    verify_gate(manifest, "B")
    if manifest.visual_check_required and not manifest.raw.get("visual_check_confirmed"):
        raise GateDenied("Visual check required but not confirmed. Default deny.")
    check_cpu_quota_and_maybe_defer()

    if not manifest.backup_required:
        raise GateDenied("CRITICAL action without backup_required=true is refused.")
    backup_path = create_backup_manifest(
        manifest.allowed_action.get("target_paths", []), manifest.manifest_sha256[:12]
    )
    if backup_path is None:
        raise GateDenied("CRITICAL action requires an existing backupable target; none found.")

    raise GateDenied(
        "Gate B production execution is NOT implemented in this reference. "
        "This design task does not authorize any production action."
    )


if __name__ == "__main__":
    print(
        "This is a design/reference module for TASK_010. It performs no "
        "network or production I/O when run directly and must not be "
        "deployed or executed against real PythonAnywhere infrastructure "
        "as part of this task.",
        file=sys.stderr,
    )
    sys.exit(0)
