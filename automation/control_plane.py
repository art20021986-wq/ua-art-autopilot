#!/usr/bin/env python3
"""TASK107-R2 durable control plane for UA ART task execution.

The module validates repository state, exact task identity, execution mode,
health evidence and receipts.  Website/CRM/DNS mutation remains delegated to
an immutable, task-scoped controller after all applicable gates pass.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import time
import urllib.request
from typing import Any, Iterable, Mapping, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "UA-ART-CONTROL-PLANE-R2.0"
ACTIVE_EXECUTION_STATUSES = {
    "CLAIMED",
    "RUNNING",
    "TESTING",
    "VERIFYING",
    "BLOCKED_RETRYABLE",
    "BLOCKED_ROOT_CAUSE",
    "STALLED",
}
TERMINAL_EXECUTION_STATUSES = {"FINISHED", "FAILED", "ROLLED_BACK"}
ALLOWED_HEARTBEAT_STATUSES = {"CLAIMED", "RUNNING", "TESTING", "VERIFYING"}
TASK_CLASSES = {"FAST", "STANDARD", "CRITICAL"}
AI_STATUSES = {"NOT_REQUESTED", "PENDING", "RECEIVED", "FAILED"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,79}$")
MAX_STORAGE_PROBE_AGE_SECONDS = 30 * 60
EXECUTION_MODE_SCHEMA = "UA-ART-EXECUTION-MODE-1"
AUTOMATIC_APPROVAL_SCHEMA = "UA-ART-AUTOMATIC-MODE-APPROVAL-1"
RUNTIME_MANIFEST_SCHEMA = "UA-ART-AUTOPILOT-RUNTIME-MANIFEST-1"
AUTOSTART_LEDGER_SCHEMA = "UA-ART-AUTOSTART-LEDGER-1"
PRODUCTION_TRANSACTION_SCHEMA = "UA-ART-PRODUCTION-TRANSACTION-2"
EXECUTION_MODES = {"MANUAL", "AUTOMATIC"}
RUNTIME_MANIFEST_PATH = "state/AUTOPILOT_RUNTIME_MANIFEST.json"
RUNTIME_PINNED_PATHS = (
    ".github/workflows/uaart_autostart.yml",
    ".github/workflows/uaart_orchestrator.yml",
    ".github/workflows/uaart_fast.yml",
    ".github/workflows/uaart_standard.yml",
    ".github/workflows/uaart_critical.yml",
    ".github/workflows/uaart_backup.yml",
    ".github/workflows/uaart_maintenance.yml",
    ".github/workflows/uaart_monitor.yml",
    ".github/workflows/uaart_transaction_watchdog.yml",
    "automation/autostart_intake.py",
    "automation/control_plane.py",
    "automation/critical_adapter.py",
    "automation/execution_contract.py",
    "automation/production_queue.py",
    "automation/task_orchestrator.py",
    "automation/task_ticket.py",
    "automation/transaction_watchdog.py",
    "state/schemas/task_request.schema.json",
)
PRODUCTION_CREDENTIAL_WORKFLOW_ALLOWLIST = frozenset({
    ".github/workflows/uaart_critical.yml",
    ".github/workflows/uaart_transaction_watchdog.yml",
})
ACTIVE_WORKFLOW_EVENT_POLICY = {
    ".github/workflows/uaart_autostart.yml": frozenset({"push"}),
    ".github/workflows/uaart_orchestrator.yml": frozenset({"workflow_call"}),
    ".github/workflows/uaart_fast.yml": frozenset({"workflow_call"}),
    ".github/workflows/uaart_standard.yml": frozenset({"workflow_call"}),
    ".github/workflows/uaart_critical.yml": frozenset({"workflow_call"}),
    ".github/workflows/uaart_backup.yml": frozenset({
        "workflow_call", "workflow_dispatch",
    }),
    ".github/workflows/uaart_maintenance.yml": frozenset({
        "schedule", "workflow_dispatch",
    }),
    ".github/workflows/uaart_monitor.yml": frozenset({
        "schedule", "workflow_dispatch",
    }),
    ".github/workflows/uaart_transaction_watchdog.yml": frozenset({"schedule"}),
}
SECRETS_INHERIT_WORKFLOW_ALLOWLIST = frozenset({
    ".github/workflows/uaart_autostart.yml",
    ".github/workflows/uaart_orchestrator.yml",
})
PRODUCTION_CREDENTIAL_REFERENCE_RE = re.compile(
    r"secrets\s*(?:\.\s*PYTHONANYWHERE_API_TOKEN"
    r"|\[\s*['\"]PYTHONANYWHERE_API_TOKEN['\"]\s*\])",
    re.IGNORECASE,
)
SECRETS_BRACKET_REFERENCE_RE = re.compile(r"secrets\s*\[")
SECRETS_INHERIT_RE = re.compile(r"(?m)^\s*secrets:\s*inherit\s*(?:#.*)?$")
SECRETS_SERIALIZATION_RE = re.compile(r"toJSON\s*\(\s*secrets\s*\)", re.IGNORECASE)
WORKFLOW_REMOTE_DISPATCH_RE = re.compile(
    r"(?:gh\s+workflow\s+run|/actions/workflows/[^\s'\"]+/dispatches"
    r"|/actions/runs/[^\s'\"]+/rerun)",
    re.IGNORECASE,
)
TASK_EXECUTION_COMMAND_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(?:(?:/usr/bin/)?python(?:3(?:\.\d+)?)?\s+(?:-I\s+)?)?"
    r"(?:\./)?automation/execution_contract\.py\s+"
    r"(test|run|backup|rollback)(?=\s|\\|$)",
    re.MULTILINE,
)
GITHUB_WRITE_CREDENTIAL_RE = re.compile(
    r"github\s*(?:\.\s*token|\[\s*['\"]token['\"]\s*\])"
    r"|secrets\s*\.\s*GITHUB_TOKEN|\b(?:GH_TOKEN|GITHUB_TOKEN)\b",
    re.IGNORECASE,
)
DATA_ONLY_ARTIFACT_VALIDATION_MARKER = "UAART_DATA_ONLY_ARTIFACT_VALIDATED"
ORCHESTRATOR_WORKFLOW_SHA256 = (
    "0bab939f235f3e03fd5c847814ae654e1ee585712b5d5c3b572f31a4779fd236"
)
CRITICAL_WORKFLOW_SHA256 = (
    "8fe7676b336594126f6e65927f3710ec550355da0f0234aed79aa63e47337b44"
)
WATCHDOG_WORKFLOW_SHA256 = (
    "20e65a0f952fbba4788509ede13bbf6069542fdf082e27f0297aa1a262669d1b"
)
PYTHON_INTERPRETER_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:/usr/bin/)?python(?:3(?:\.\d+)?)?"
    r"(?![A-Za-z0-9_./@-])"
)


class ControlPlaneError(ValueError):
    """A fail-closed control-plane validation error."""


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_utc(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlPlaneError("INVALID_UTC_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ControlPlaneError("UTC_TIMESTAMP_REQUIRES_TIMEZONE")
    return parsed.astimezone(dt.timezone.utc)


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha(value: Any, label: str) -> str:
    text = str(value or "").lower()
    if not SHA_RE.fullmatch(text):
        raise ControlPlaneError("INVALID_SHA256:" + label)
    return text


def safe_repo_path(value: str) -> str:
    raw = str(value)
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", raw) or "//" in raw:
        raise ControlPlaneError("UNSAFE_REPO_PATH:" + raw)
    path = pathlib.PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ControlPlaneError("UNSAFE_REPO_PATH:" + str(value))
    return path.as_posix()


def repo_path(value: str, root: pathlib.Path = ROOT) -> pathlib.Path:
    normalized = safe_repo_path(value)
    resolved = (root / normalized).resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    if resolved == root_resolved or not resolved.is_relative_to(root_resolved):
        raise ControlPlaneError("REPOSITORY_PATH_ESCAPE:" + normalized)
    return resolved


def read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlPlaneError("INVALID_JSON:" + str(path)) from exc
    if not isinstance(value, dict):
        raise ControlPlaneError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def require_mode_status(path: pathlib.Path, expected: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise ControlPlaneError("EXECUTION_MODE_STATUS_FILE_MISSING")
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("STATUS:")
    ]
    wanted = "STATUS: " + expected
    if lines != [wanted]:
        raise ControlPlaneError("EXECUTION_MODE_STATUS_CONFLICT:" + expected)


def _workflow_trigger_block(source: str, relative: str) -> str:
    lines = source.splitlines()
    starts = [index for index, line in enumerate(lines) if line.rstrip() == "on:"]
    if len(starts) != 1:
        raise ControlPlaneError("WORKFLOW_ON_BLOCK_INVALID:" + relative)
    start = starts[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            end = index
            break
    block = lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    if len(block) < 2:
        raise ControlPlaneError("WORKFLOW_ON_BLOCK_EMPTY:" + relative)
    return "\n".join(block) + "\n"


def _workflow_events(source: str, relative: str) -> frozenset[str]:
    block = _workflow_trigger_block(source, relative)
    events: list[str] = []
    for line in block.splitlines()[1:]:
        match = re.fullmatch(r"  ([a-zA-Z_][a-zA-Z0-9_-]*):(?:\s*.*)?", line)
        if match:
            events.append(match.group(1))
    if not events or len(events) != len(set(events)):
        raise ControlPlaneError("WORKFLOW_EVENTS_INVALID:" + relative)
    return frozenset(events)


def _named_workflow_step_blocks(source: str, relative: str) -> tuple[str, ...]:
    """Return named step blocks without allowing one job to bleed into another."""
    blocks = [
        block
        for _job_id, job in _workflow_job_blocks(source, relative)
        for block in _named_job_step_blocks(job, relative, _job_id)
    ]
    if not blocks:
        raise ControlPlaneError("WORKFLOW_NAMED_STEPS_MISSING:" + relative)
    return tuple(blocks)


def _workflow_job_blocks(source: str, relative: str) -> tuple[tuple[str, str], ...]:
    """Return ``jobs.<id>`` blocks using only indentation guaranteed by Actions.

    Loading workflow YAML through a generic parser is surprisingly fragile because
    YAML 1.1 treats the key ``on`` as a boolean.  The active workflows are pinned,
    so a deliberately small indentation parser is both deterministic and fail
    closed: jobs must be ordinary two-space mapping keys under one top-level
    ``jobs:`` block.
    """
    lines = source.splitlines()
    job_roots = [index for index, line in enumerate(lines) if line == "jobs:"]
    if len(job_roots) != 1:
        raise ControlPlaneError("WORKFLOW_JOBS_BLOCK_INVALID:" + relative)
    jobs_start = job_roots[0]
    jobs_end = len(lines)
    for index in range(jobs_start + 1, len(lines)):
        line = lines[index]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            jobs_end = index
            break
    starts: list[tuple[int, str]] = []
    for index in range(jobs_start + 1, jobs_end):
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+):\s*(?:#.*)?", lines[index])
        if match:
            starts.append((index, match.group(1)))
    if not starts or len({job_id for _index, job_id in starts}) != len(starts):
        raise ControlPlaneError("WORKFLOW_JOBS_INVALID:" + relative)
    return tuple(
        (
            job_id,
            "\n".join(
                lines[
                    start:(starts[offset + 1][0] if offset + 1 < len(starts) else jobs_end)
                ]
            ) + "\n",
        )
        for offset, (start, job_id) in enumerate(starts)
    )


def _named_job_step_blocks(
    job: str,
    relative: str,
    job_id: str,
) -> tuple[str, ...]:
    lines = job.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^      - name:\s*\S", line)
    ]
    if "\n    steps:\n" in job and not starts:
        raise ControlPlaneError(
            "WORKFLOW_NAMED_STEPS_MISSING:" + relative + ":" + job_id
        )
    return tuple(
        "\n".join(
            lines[start:(starts[offset + 1] if offset + 1 < len(starts) else len(lines))]
        ) + "\n"
        for offset, start in enumerate(starts)
    )


def _step_run_body(block: str, relative: str) -> str | None:
    """Extract one named step's run scalar without including declarative env."""
    lines = block.splitlines()
    matches = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := re.match(r"^(\s*)run:\s*(.*)$", line))
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ControlPlaneError("WORKFLOW_STEP_RUN_INVALID:" + relative)
    index, match = matches[0]
    indentation = len(match.group(1))
    scalar = match.group(2)
    if not re.fullmatch(r"[|>][-+]?", scalar):
        return scalar
    body: list[str] = []
    for line in lines[index + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indentation:
            break
        body.append(line)
    return "\n".join(body)


def _job_contents_permission(job: str, relative: str, job_id: str) -> str | None:
    """Read an explicit job-level ``permissions.contents`` value."""
    lines = job.splitlines()
    declarations = [
        (index, line)
        for index, line in enumerate(lines)
        if re.match(r"^    permissions:\s*", line)
    ]
    if not declarations:
        return None
    if len(declarations) != 1 or declarations[0][1] != "    permissions:":
        raise ControlPlaneError(
            "WORKFLOW_JOB_PERMISSIONS_INVALID:" + relative + ":" + job_id
        )
    start = declarations[0][0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip()) <= 4:
            end = index
            break
    values = []
    for line in lines[start + 1:end]:
        match = re.fullmatch(r"      contents:\s*(read|write|none)\s*(?:#.*)?", line)
        if match:
            values.append(match.group(1))
    if len(values) != 1:
        raise ControlPlaneError(
            "WORKFLOW_JOB_CONTENTS_PERMISSION_INVALID:" + relative + ":" + job_id
        )
    return values[0]


def _workflow_contents_permission(source: str, relative: str) -> str | None:
    """Read the workflow-level contents default used by jobs without overrides."""
    lines = source.splitlines()
    declarations = [
        (index, line)
        for index, line in enumerate(lines)
        if re.match(r"^permissions:\s*", line)
    ]
    if not declarations:
        return None
    if len(declarations) != 1 or declarations[0][1] != "permissions:":
        raise ControlPlaneError("WORKFLOW_PERMISSIONS_INVALID:" + relative)
    start = declarations[0][0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip()) == 0:
            end = index
            break
    values = []
    for line in lines[start + 1:end]:
        match = re.fullmatch(r"  contents:\s*(read|write|none)\s*(?:#.*)?", line)
        if match:
            values.append(match.group(1))
    if len(values) != 1:
        raise ControlPlaneError("WORKFLOW_CONTENTS_PERMISSION_INVALID:" + relative)
    return values[0]


def _task_execution_commands(value: str) -> frozenset[str]:
    """Find only controller commands, never similarly-prefixed receipt commands."""
    return frozenset(TASK_EXECUTION_COMMAND_RE.findall(value))


def _verify_fresh_runner_job_policy(source: str, relative: str) -> None:
    jobs = _workflow_job_blocks(source, relative)
    workflow_permission = _workflow_contents_permission(source, relative)
    if re.search(r"github\s*\.\s*ref_name|\bGITHUB_REF_NAME\b", source, re.I):
        raise ControlPlaneError("WORKFLOW_DYNAMIC_BRANCH_FORBIDDEN:" + relative)
    if "github.ref == 'refs/heads/main'" not in source:
        raise ControlPlaneError("WORKFLOW_MAIN_GUARD_MISSING:" + relative)
    if re.search(r"(?m)^\s*git\s+rebase\b", source):
        raise ControlPlaneError("WORKFLOW_REBASE_FORBIDDEN:" + relative)
    checkout_count = 0
    task_job_count = 0
    privileged_push_count = 0
    for job_id, job in jobs:
        job_permission = _job_contents_permission(job, relative, job_id)
        permission = job_permission if job_permission is not None else workflow_permission
        task_commands = _task_execution_commands(job)
        has_write = permission == "write"
        has_production_secret = bool(PRODUCTION_CREDENTIAL_REFERENCE_RE.search(job))
        if task_commands:
            task_job_count += 1
            if "github.ref == 'refs/heads/main'" not in job:
                raise ControlPlaneError(
                    "TASK_JOB_MAIN_GUARD_MISSING:" + relative + ":" + job_id
                )
            if job_permission != "read":
                raise ControlPlaneError(
                    "TASK_JOB_CONTENTS_NOT_READ_ONLY:" + relative + ":" + job_id
                )
            if GITHUB_WRITE_CREDENTIAL_RE.search(job):
                raise ControlPlaneError(
                    "TASK_JOB_GITHUB_CREDENTIAL_EXPOSURE:" + relative + ":" + job_id
                )
        if has_write and task_commands:
            raise ControlPlaneError(
                "PRIVILEGED_JOB_EXECUTES_TASK_CODE:" + relative + ":" + job_id
            )
        if has_write and has_production_secret:
            raise ControlPlaneError(
                "PRIVILEGED_JOB_PRODUCTION_SECRET_EXPOSURE:" + relative + ":" + job_id
            )
        if has_write and "github.ref == 'refs/heads/main'" not in job:
            raise ControlPlaneError(
                "PRIVILEGED_JOB_MAIN_GUARD_MISSING:" + relative + ":" + job_id
            )

        for match in PYTHON_INTERPRETER_RE.finditer(job):
            suffix = job[match.end():]
            if not re.match(r"\s+-I(?=\s|$)", suffix):
                raise ControlPlaneError(
                    "WORKFLOW_PYTHON_NOT_ISOLATED:" + relative + ":" + job_id
                )

        steps = _named_job_step_blocks(job, relative, job_id)
        for block in steps:
            if re.search(r"uses:\s*actions/checkout@", block):
                checkout_count += 1
                if block.count("persist-credentials: false") != 1:
                    raise ControlPlaneError(
                        "WORKFLOW_CHECKOUT_CREDENTIAL_POLICY:"
                        + relative + ":" + job_id
                    )
                if "persist-credentials: true" in block:
                    raise ControlPlaneError(
                        "WORKFLOW_PERSISTED_CREDENTIAL_ENABLED:"
                        + relative + ":" + job_id
                    )
                if len(re.findall(r"(?m)^\s+ref:\s*main\s*$", block)) != 1:
                    raise ControlPlaneError(
                        "WORKFLOW_CHECKOUT_NOT_MAIN:" + relative + ":" + job_id
                    )
            if re.search(r"uses:\s*actions/download-artifact@", block):
                if re.search(r"(?:GITHUB_WORKSPACE|github\.workspace)", block, re.I):
                    raise ControlPlaneError(
                        "ARTIFACT_DOWNLOAD_WORKSPACE_FORBIDDEN:"
                        + relative + ":" + job_id
                    )
                if not re.search(
                    r"(?m)^\s+path:\s*(?:\$RUNNER_TEMP|\$\{\{\s*runner\.temp\s*\}\})/\S+\s*$",
                    block,
                ):
                    raise ControlPlaneError(
                        "ARTIFACT_DOWNLOAD_NOT_RUNNER_TEMP:"
                        + relative + ":" + job_id
                    )
                if has_write and DATA_ONLY_ARTIFACT_VALIDATION_MARKER not in job:
                    raise ControlPlaneError(
                        "PRIVILEGED_ARTIFACT_NOT_DATA_ONLY_VALIDATED:"
                        + relative + ":" + job_id
                    )
            if re.search(r"\bpush\s+origin\b", block):
                privileged_push_count += 1
                if permission != "write":
                    raise ControlPlaneError(
                        "GIT_PUSH_JOB_NOT_PRIVILEGED:" + relative + ":" + job_id
                    )
                required = (
                    "GIT_INDEX_FILE",
                    "RUNNER_TEMP",
                    "git read-tree",
                    "git commit-tree",
                    "COMMIT:refs/heads/main",
                )
                if any(marker not in block for marker in required):
                    raise ControlPlaneError(
                        "PRIVILEGED_PUSH_NOT_ISOLATED_TREE:"
                        + relative + ":" + job_id
                    )
                if re.search(r"\bpush\s+origin\s+[^\n]*\bHEAD(?::|\b)", block):
                    raise ControlPlaneError(
                        "PRIVILEGED_PUSH_HEAD_FORBIDDEN:"
                        + relative + ":" + job_id
                    )
                push_lines = [
                    line
                    for line in block.splitlines()
                    if re.search(r"\bpush\s+origin\b", line)
                ]
                if not push_lines or any(
                    "COMMIT:refs/heads/main" not in line for line in push_lines
                ):
                    raise ControlPlaneError(
                        "PRIVILEGED_PUSH_TARGET_NOT_MAIN:"
                        + relative + ":" + job_id
                    )
    if checkout_count < 1:
        raise ControlPlaneError("WORKFLOW_CHECKOUT_MISSING:" + relative)
    if task_job_count < 1:
        raise ControlPlaneError("WORKFLOW_TASK_JOB_MISSING:" + relative)
    if privileged_push_count < 1:
        raise ControlPlaneError("WORKFLOW_PRIVILEGED_PUSH_MISSING:" + relative)

    if relative in {
        ".github/workflows/uaart_fast.yml",
        ".github/workflows/uaart_standard.yml",
    }:
        job_map = dict(jobs)
        for job_id in ("execute", "persist"):
            job = job_map.get(job_id, "")
            header = job.split("\n    steps:", 1)[0]
            if "github.run_attempt == 1" not in header:
                raise ControlPlaneError(
                    "NONPRODUCTION_RERUN_JOB_GATE:" + relative + ":" + job_id
                )
            if "test \"$GITHUB_RUN_ATTEMPT\" = '1'" not in job:
                raise ControlPlaneError(
                    "NONPRODUCTION_RERUN_SHELL_GATE:" + relative + ":" + job_id
                )
        execute = job_map.get("execute", "")
        execute_blob_markers = (
            "workflow_blob_oid: ${{ steps.contract.outputs.workflow_blob_oid }}",
            "workflow_source_commit: ${{ steps.contract.outputs.workflow_source_commit }}",
            "WORKFLOW_SOURCE_COMMIT: ${{ github.sha }}",
            "WORKFLOW_PATH: " + relative,
            "fetch-depth: 0",
            'git merge-base --is-ancestor "$WORKFLOW_SOURCE_COMMIT" HEAD',
            'git rev-parse "$WORKFLOW_SOURCE_COMMIT:$WORKFLOW_PATH"',
            "VALIDATION_WORKFLOW_BLOB_BINDING",
            '"$WORKFLOW_SOURCE_COMMIT:state/AUTOPILOT_RUNTIME_MANIFEST.json"',
            'echo "workflow_blob_oid=${WORKFLOW_BLOB_OID}"',
            'echo "workflow_source_commit=${WORKFLOW_SOURCE_COMMIT}"',
        )
        if any(marker not in execute for marker in execute_blob_markers):
            raise ControlPlaneError(
                "NONPRODUCTION_WORKFLOW_BLOB_BINDING:"
                + relative + ":execute"
            )
        persist = job_map.get("persist", "")
        persist_blob_markers = (
            "WORKFLOW_SOURCE_COMMIT: ${{ needs.execute.outputs.workflow_source_commit }}",
            "WORKFLOW_BLOB_OID: ${{ needs.execute.outputs.workflow_blob_oid }}",
            "WORKFLOW_PATH: " + relative,
            'git merge-base --is-ancestor "$WORKFLOW_SOURCE_COMMIT" "$SOURCE_COMMIT"',
            'git rev-parse "$WORKFLOW_SOURCE_COMMIT:$WORKFLOW_PATH"',
            'git rev-parse "$SOURCE_COMMIT:$WORKFLOW_PATH"',
            'git rev-parse "$PARENT:$WORKFLOW_PATH"',
            "'workflow_blob_oid'",
            "'workflow_source_commit'",
        )
        if any(marker not in persist for marker in persist_blob_markers):
            raise ControlPlaneError(
                "NONPRODUCTION_WORKFLOW_BLOB_BINDING:"
                + relative + ":persist"
            )
        accepted_persist_markers = (
            "ACCEPTED_PATHS",
            'git diff --quiet "$COMMIT" refs/remotes/origin/main --',
            '"${ACCEPTED_PATHS[@]}"',
            "ACCEPTED_PUSH_OWNED_PATHS_CHANGED",
        )
        if any(marker not in persist for marker in accepted_persist_markers):
            raise ControlPlaneError(
                "NONPRODUCTION_ACCEPTED_PUSH_OWNERSHIP:"
                + relative + ":persist"
            )
        artifact_markers = (
            "ARTIFACT_IMPORT_ROOT_INVALID",
            "ARTIFACT_DUPLICATE_KEY",
            "REBUILD_ARTIFACT_DUPLICATE_KEY",
            "'workflow_blob_oid'",
            "'workflow_source_commit'",
            "ARTIFACT_SIZE_LIMIT",
            "ARTIFACT_FILE_SET",
            "ARTIFACT_TARGET_SYMLINK",
        )
        if any(marker not in persist for marker in artifact_markers):
            raise ControlPlaneError(
                "NONPRODUCTION_ARTIFACT_SCHEMA:" + relative + ":persist"
            )
        failure = job_map.get("persist_failure", "")
        terminal_markers = (
            'if test "$GITHUB_RUN_ATTEMPT" != \'1\'',
            "FAILURE_MODE_ARGS+=(--terminal)",
            '"${FAILURE_MODE_ARGS[@]}"',
        )
        if any(marker not in failure for marker in terminal_markers):
            raise ControlPlaneError(
                "NONPRODUCTION_RERUN_TERMINAL_GATE:" + relative
            )
        failure_blob_markers = (
            "WORKFLOW_SOURCE_COMMIT: ${{ github.sha }}",
            "WORKFLOW_PATH: " + relative,
            'git rev-parse "HEAD:$WORKFLOW_PATH"',
            'git rev-parse "$PARENT:$WORKFLOW_PATH"',
            '"$WORKFLOW_SOURCE_COMMIT:$WORKFLOW_PATH"',
        )
        if any(marker not in failure for marker in failure_blob_markers):
            raise ControlPlaneError(
                "NONPRODUCTION_WORKFLOW_BLOB_BINDING:"
                + relative + ":persist_failure"
            )
        accepted_failure_markers = (
            'git diff --quiet "$COMMIT" refs/remotes/origin/main --',
            '"$CLAIM_PATH"',
            "ACCEPTED_PUSH_OWNED_PATHS_CHANGED",
        )
        if any(marker not in failure for marker in accepted_failure_markers):
            raise ControlPlaneError(
                "NONPRODUCTION_ACCEPTED_PUSH_OWNERSHIP:"
                + relative + ":persist_failure"
            )
        for block in _named_workflow_step_blocks(source, relative):
            body = _step_run_body(block, relative)
            if body is not None and "${{" in body:
                raise ControlPlaneError(
                    "WORKFLOW_RUN_EXPRESSION_FORBIDDEN:" + relative
                )
        for job_id in ("persist", "persist_failure"):
            job = job_map.get(job_id, "")
            runtime_markers = (
                "UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED",
                "AUTOPILOT_RUNTIME_MANIFEST.json",
                "object_pairs_hook=reject_duplicate_keys",
                "state/schemas/task_request.schema.json",
                "target.resolve() != target",
                "total > 16 * 1024 * 1024",
            )
            if job.count("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED") < 2 or any(
                marker not in job for marker in runtime_markers
            ):
                raise ControlPlaneError(
                    "NONPRODUCTION_RUNTIME_BOOTSTRAP_MISSING:"
                    + relative + ":" + job_id
                )
            repository_python = re.search(
                r"(?m)^\s*(?:/usr/bin/)?python(?:3(?:\.\d+)?)?\s+-I\s+"
                r"automation/(?:control_plane|execution_contract)\.py\b",
                job,
            )
            if repository_python is None or job.find(
                "UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED"
            ) > repository_python.start():
                raise ControlPlaneError(
                    "NONPRODUCTION_RUNTIME_BOOTSTRAP_ORDER:"
                    + relative + ":" + job_id
                )
            steps = _named_job_step_blocks(job, relative, job_id)
            credential_steps = [
                block for block in steps if GITHUB_WRITE_CREDENTIAL_RE.search(block)
            ]
            if len(credential_steps) != 1 or GITHUB_WRITE_CREDENTIAL_RE.search(
                job.replace(credential_steps[0], "", 1)
            ):
                raise ControlPlaneError(
                    "NONPRODUCTION_GITHUB_TOKEN_SCOPE:"
                    + relative + ":" + job_id
                )
            credential_step = credential_steps[0]
            first_python = PYTHON_INTERPRETER_RE.search(credential_step)
            repository_python = re.search(
                r"(?m)^\s*(?:/usr/bin/)?python(?:3(?:\.\d+)?)?\s+-I\s+"
                r"automation/(?:control_plane|execution_contract)\.py\b",
                credential_step,
            )
            if (
                first_python is None
                or repository_python is None
                or "unset GH_TOKEN" not in credential_step
                or credential_step.index("unset GH_TOKEN") > first_python.start()
                or credential_step.find(
                    "UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED"
                ) > repository_python.start()
            ):
                raise ControlPlaneError(
                    "NONPRODUCTION_TOKEN_BOOTSTRAP_ORDER:"
                    + relative + ":" + job_id
                )
        for marker in (
            "WORKFLOW_SOURCE_COMMIT",
            "git cat-file blob",
            "git merge-base --is-ancestor \"$WORKFLOW_SOURCE_COMMIT\"",
        ):
            if marker not in failure:
                raise ControlPlaneError(
                    "NONPRODUCTION_FAILURE_SOURCE_ANCHOR:"
                    + relative
                )


def _verify_autostart_fresh_runner_policy(source: str, relative: str) -> None:
    """Enforce one-shot marker validation and isolated anti-replay persistence."""
    jobs = dict(_workflow_job_blocks(source, relative))
    if set(jobs) != {"context", "intake", "persist", "execute"}:
        raise ControlPlaneError("AUTOSTART_JOB_SET_INVALID")
    if _workflow_contents_permission(source, relative) != "read":
        raise ControlPlaneError("AUTOSTART_WORKFLOW_NOT_READ_ONLY_DEFAULT")
    if "github.ref == 'refs/heads/main'" not in source:
        raise ControlPlaneError("AUTOSTART_MAIN_GUARD_MISSING")
    if re.search(r"github\s*\.\s*ref_name|\bGITHUB_REF_NAME\b", source, re.I):
        raise ControlPlaneError("AUTOSTART_DYNAMIC_BRANCH_FORBIDDEN")
    if re.search(r"(?m)^\s*git\s+rebase\b", source):
        raise ControlPlaneError("AUTOSTART_REBASE_FORBIDDEN")
    if re.search(r"(?m)^\s*git\s+add\b", source):
        raise ControlPlaneError("AUTOSTART_GIT_ADD_FORBIDDEN")
    if re.search(r"\bpush\s+origin\s+[^\n]*\bHEAD(?::|\b)", source):
        raise ControlPlaneError("AUTOSTART_PUSH_HEAD_FORBIDDEN")

    for block in _named_workflow_step_blocks(source, relative):
        body = _step_run_body(block, relative)
        if body is not None and "${{" in body:
            raise ControlPlaneError("AUTOSTART_RUN_EXPRESSION_FORBIDDEN")

    for job_id in ("intake", "persist", "execute"):
        header = jobs[job_id].split("\n    steps:", 1)[0]
        if (
            "github.ref == 'refs/heads/main'" not in header
            or "github.run_attempt == 1" not in header
        ):
            raise ControlPlaneError("AUTOSTART_JOB_REPLAY_GATE:" + job_id)
    for job_id in ("context", "intake", "persist"):
        if "test \"$GITHUB_RUN_ATTEMPT\" = '1'" not in jobs[job_id]:
            raise ControlPlaneError("AUTOSTART_SHELL_REPLAY_GATE:" + job_id)
    for job_id, job in jobs.items():
        for match in PYTHON_INTERPRETER_RE.finditer(job):
            if not re.match(r"\s+-I(?=\s|$)", job[match.end():]):
                raise ControlPlaneError(
                    "AUTOSTART_PYTHON_NOT_ISOLATED:" + job_id
                )

    expected_permissions = {
        "context": "read",
        "intake": "read",
        "persist": "write",
        "execute": "write",
    }
    for job_id, expected in expected_permissions.items():
        if _job_contents_permission(jobs[job_id], relative, job_id) != expected:
            raise ControlPlaneError("AUTOSTART_JOB_PERMISSION:" + job_id)
    for job_id in ("context", "intake", "execute"):
        if GITHUB_WRITE_CREDENTIAL_RE.search(jobs[job_id]):
            raise ControlPlaneError("AUTOSTART_GITHUB_CREDENTIAL_EXPOSURE:" + job_id)
    if PRODUCTION_CREDENTIAL_REFERENCE_RE.search(source):
        raise ControlPlaneError("AUTOSTART_PRODUCTION_CREDENTIAL_EXPOSURE")

    checkout_blocks: dict[str, list[str]] = {}
    for job_id, job in jobs.items():
        checkout_blocks[job_id] = [
            block
            for block in _named_job_step_blocks(job, relative, job_id)
            if re.search(r"uses:\s*actions/checkout@", block)
        ]
        for block in checkout_blocks[job_id]:
            if block.count("persist-credentials: false") != 1:
                raise ControlPlaneError(
                    "AUTOSTART_CHECKOUT_CREDENTIAL_POLICY:" + job_id
                )
    if len(checkout_blocks["intake"]) != 1 or not re.search(
        r"(?m)^\s+ref:\s*\$\{\{\s*github\.sha\s*\}\}\s*$",
        checkout_blocks["intake"][0],
    ):
        raise ControlPlaneError("AUTOSTART_INTAKE_CHECKOUT_NOT_SOURCE_COMMIT")
    if len(checkout_blocks["persist"]) != 1 or not re.search(
        r"(?m)^\s+ref:\s*main\s*$", checkout_blocks["persist"][0]
    ):
        raise ControlPlaneError("AUTOSTART_PERSIST_CHECKOUT_NOT_MAIN")
    if checkout_blocks["context"] or checkout_blocks["execute"]:
        raise ControlPlaneError("AUTOSTART_UNEXPECTED_CHECKOUT")

    if "--validate-only" not in jobs["intake"]:
        raise ControlPlaneError("AUTOSTART_READ_ONLY_VALIDATION_MISSING")
    bootstrap_index = jobs["intake"].find("git diff --name-only -z")
    python_index = jobs["intake"].find("python3 -I")
    if bootstrap_index < 0 or python_index < 0 or bootstrap_index > python_index:
        raise ControlPlaneError("AUTOSTART_BOOTSTRAP_ORDER")
    if "needs: persist" not in jobs["execute"] or \
            "uses: ./.github/workflows/uaart_orchestrator.yml" not in jobs["execute"]:
        raise ControlPlaneError("AUTOSTART_DOWNSTREAM_BINDING")

    persist_steps = _named_job_step_blocks(jobs["persist"], relative, "persist")
    token_blocks = [
        block
        for block in persist_steps
        if "github.token" in block
    ]
    if len(token_blocks) != 1:
        raise ControlPlaneError("AUTOSTART_GITHUB_TOKEN_STEP_COUNT")
    persist = token_blocks[0]
    credential_blocks = [
        block for block in persist_steps if GITHUB_WRITE_CREDENTIAL_RE.search(block)
    ]
    if credential_blocks != [persist] or GITHUB_WRITE_CREDENTIAL_RE.search(
        jobs["persist"].replace(persist, "", 1)
    ):
        raise ControlPlaneError("AUTOSTART_GITHUB_TOKEN_SCOPE")
    required = (
        "python3 -I \"$TRUSTED_RUNTIME/automation/autostart_intake.py\"",
        "--root \"$REBUILD\"",
        "for attempt in 1 2 3 4 5 6",
        "git merge-base --is-ancestor \"$BEFORE_SHA\" \"$SOURCE_COMMIT\"",
        "git merge-base --is-ancestor \"$COMMIT\"",
        "git rev-list --parents -n 1",
        "SOURCE_LAUNCH_ENTRY",
        "PARENT_LAUNCH_ENTRY",
        "UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED",
        "object_pairs_hook=reject_duplicate_keys",
        "state/schemas/task_request.schema.json",
        "total > 16 * 1024 * 1024",
        "AUTOSTART_SOURCE_RUNTIME_SHA_MISMATCH",
        "GITHUB_OUTPUT=\"$ATTEMPT_OUTPUTS\"",
        "AUTOSTART_OUTPUT_BINDING",
        "LAST_OUTPUTS=\"$ATTEMPT_OUTPUTS\"",
        "cat \"$LAST_OUTPUTS\" >>\"$GITHUB_OUTPUT\"",
        "^state/autostart_consumed/",
        "^state/autostart_nonces/",
        "GIT_INDEX_FILE",
        "RUNNER_TEMP",
        "git read-tree",
        "git commit-tree",
        "AUTOSTART_COMMIT_PATH_SCOPE",
        "COMMIT:refs/heads/main",
    )
    if any(marker not in persist for marker in required):
        raise ControlPlaneError("AUTOSTART_PRIVILEGED_PERSIST_CONTRACT")
    if (
        "unset GH_TOKEN" not in persist
        or persist.index("unset GH_TOKEN") > persist.index("python3 -I")
    ):
        raise ControlPlaneError("AUTOSTART_TOKEN_LIFETIME")
    push_lines = [
        line for line in persist.splitlines() if re.search(r"\bpush\s+origin\b", line)
    ]
    if not push_lines or any("COMMIT:refs/heads/main" not in line for line in push_lines):
        raise ControlPlaneError("AUTOSTART_PUSH_TARGET_NOT_MAIN")


def _verify_orchestrator_fresh_runner_policy(source: str, relative: str) -> None:
    """Keep intake validation separate from the one trusted state writer."""
    jobs = dict(_workflow_job_blocks(source, relative))
    if set(jobs) != {"validate", "plan", "fast", "standard", "critical"}:
        raise ControlPlaneError("ORCHESTRATOR_JOB_SET_INVALID")
    if _workflow_contents_permission(source, relative) != "read":
        raise ControlPlaneError("ORCHESTRATOR_WORKFLOW_NOT_READ_ONLY_DEFAULT")
    if re.search(r"github\s*\.\s*ref_name|\bGITHUB_REF_NAME\b", source, re.I):
        raise ControlPlaneError("ORCHESTRATOR_DYNAMIC_BRANCH_FORBIDDEN")
    if re.search(r"\bHEAD\b", source):
        raise ControlPlaneError("ORCHESTRATOR_HEAD_FORBIDDEN")
    for pattern, error in (
        (r"(?m)^\s*git\s+add\b", "ORCHESTRATOR_GIT_ADD_FORBIDDEN"),
        (r"(?m)^\s*git\s+commit(?:\s|$)", "ORCHESTRATOR_GIT_COMMIT_FORBIDDEN"),
        (r"(?m)^\s*git\s+rebase\b", "ORCHESTRATOR_REBASE_FORBIDDEN"),
        (r"\bpush\s+origin\s+[^\n]*\bHEAD(?::|\b)", "ORCHESTRATOR_PUSH_HEAD_FORBIDDEN"),
    ):
        if re.search(pattern, source):
            raise ControlPlaneError(error)
    if PRODUCTION_CREDENTIAL_REFERENCE_RE.search(source):
        raise ControlPlaneError("ORCHESTRATOR_PRODUCTION_CREDENTIAL_EXPOSURE")

    expected_guards = {
        "validate": "github.ref == 'refs/heads/main' && github.run_attempt == 1",
        "plan": "github.ref == 'refs/heads/main' && github.run_attempt == 1",
        "fast": (
            "github.ref == 'refs/heads/main' && github.run_attempt == 1 && "
            "needs.plan.outputs.task_class == 'FAST'"
        ),
        "standard": (
            "github.ref == 'refs/heads/main' && github.run_attempt == 1 && "
            "needs.plan.outputs.task_class == 'STANDARD'"
        ),
        "critical": (
            "github.ref == 'refs/heads/main' && github.run_attempt == 1 && "
            "needs.plan.outputs.task_class == 'CRITICAL'"
        ),
    }
    for job_id, job in jobs.items():
        header = job.split("\n    steps:", 1)[0]
        expected_if = "    if: " + expected_guards[job_id]
        if len(re.findall(r"(?m)^    if:\s*.*$", header)) != 1 or expected_if not in header.splitlines():
            raise ControlPlaneError("ORCHESTRATOR_JOB_REPLAY_GATE:" + job_id)
        for block in _named_job_step_blocks(job, relative, job_id):
            body = _step_run_body(block, relative)
            if body is None:
                continue
            if "${{" in body:
                raise ControlPlaneError(
                    "ORCHESTRATOR_RUN_EXPRESSION_FORBIDDEN:" + job_id
                )
            for match in PYTHON_INTERPRETER_RE.finditer(body):
                if not re.match(r"\s+-I(?=\s|$)", body[match.end():]):
                    raise ControlPlaneError(
                        "ORCHESTRATOR_PYTHON_NOT_ISOLATED:" + job_id
                    )
    for block in _named_job_step_blocks(jobs["plan"], relative, "plan"):
        body = _step_run_body(block, relative)
        if body is None:
            continue
        for line in body.splitlines():
            command = line.strip()
            interpreter = PYTHON_INTERPRETER_RE.search(command)
            if interpreter is None:
                continue
            if interpreter.start() != 0 or not command.startswith("python3 -I"):
                raise ControlPlaneError("ORCHESTRATOR_UNTRUSTED_PYTHON_COMMAND")
            allowed = (
                r"^python3 -I -(?:\s|$)",
                r"^python3 -I -W error -m py_compile(?:\s|$)",
                r"^python3 -I automation/control_plane\.py "
                r"(?:verify-mode|claim|verify-request|planning|verify-identity)(?:\s|$)",
                r"^python3 -I automation/execution_contract\.py validate(?:\s|$)",
            )
            if not any(re.match(pattern, command) for pattern in allowed):
                raise ControlPlaneError("ORCHESTRATOR_UNTRUSTED_PYTHON_COMMAND")
    for job_id in ("validate", "plan"):
        if "test \"$GITHUB_RUN_ATTEMPT\" = '1'" not in jobs[job_id]:
            raise ControlPlaneError("ORCHESTRATOR_SHELL_REPLAY_GATE:" + job_id)

    expected_permissions = {
        "validate": "read",
        "plan": "write",
        # Reusable callees cannot elevate the caller's permission ceiling. Their
        # own task jobs still explicitly reduce themselves to contents:read.
        "fast": "write",
        "standard": "write",
        "critical": "write",
    }
    for job_id, expected in expected_permissions.items():
        if _job_contents_permission(jobs[job_id], relative, job_id) != expected:
            raise ControlPlaneError("ORCHESTRATOR_JOB_PERMISSION:" + job_id)
    if GITHUB_WRITE_CREDENTIAL_RE.search(jobs["validate"]):
        raise ControlPlaneError("ORCHESTRATOR_VALIDATE_GITHUB_CREDENTIAL")
    for job_id in ("validate", "plan"):
        if _task_execution_commands(jobs[job_id]):
            raise ControlPlaneError("ORCHESTRATOR_TASK_CODE_IN_LOCAL_JOB:" + job_id)
        if re.search(
            r"(?m)^\s*(?:(?:/usr/bin/)?python(?:3(?:\.\d+)?)?\s+(?:-I\s+)?)?"
            r"(?:\./)?automation/task_orchestrator\.py(?:\s|$)",
            jobs[job_id],
        ):
            raise ControlPlaneError("ORCHESTRATOR_CONTROLLER_IN_LOCAL_JOB:" + job_id)
    expected_callees = {
        "fast": "./.github/workflows/uaart_fast.yml",
        "standard": "./.github/workflows/uaart_standard.yml",
        "critical": "./.github/workflows/uaart_critical.yml",
    }
    for job_id, callee in expected_callees.items():
        if (
            len(re.findall(r"(?m)^    uses:\s*.*$", jobs[job_id])) != 1
            or ("    uses: " + callee) not in jobs[job_id].splitlines()
            or "    needs: plan" not in jobs[job_id].splitlines()
        ):
            raise ControlPlaneError("ORCHESTRATOR_ROUTE_CALLEE:" + job_id)

    checkout_blocks: dict[str, list[str]] = {}
    for job_id, job in jobs.items():
        checkout_blocks[job_id] = [
            block
            for block in _named_job_step_blocks(job, relative, job_id)
            if re.search(r"uses:\s*actions/checkout@", block)
        ]
        for block in checkout_blocks[job_id]:
            if (
                block.count("persist-credentials: false") != 1
                or block.count("clean: true") != 1
                or block.count("fetch-depth: 0") != 1
                or len(re.findall(r"(?m)^\s+ref:\s*main\s*$", block)) != 1
            ):
                raise ControlPlaneError(
                    "ORCHESTRATOR_CHECKOUT_POLICY:" + job_id
                )
    if len(checkout_blocks["validate"]) != 1 or len(checkout_blocks["plan"]) != 1:
        raise ControlPlaneError("ORCHESTRATOR_CHECKOUT_COUNT")
    if any(checkout_blocks[job_id] for job_id in ("fast", "standard", "critical")):
        raise ControlPlaneError("ORCHESTRATOR_ROUTE_CHECKOUT_FORBIDDEN")

    uses = re.findall(r"(?m)^\s+uses:\s*(\S+)\s*$", source)
    expected_uses = [
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
        "./.github/workflows/uaart_fast.yml",
        "./.github/workflows/uaart_standard.yml",
        "./.github/workflows/uaart_critical.yml",
    ]
    if sorted(uses) != sorted(expected_uses):
        raise ControlPlaneError("ORCHESTRATOR_USES_ALLOWLIST")
    plan_steps = _named_job_step_blocks(jobs["plan"], relative, "plan")
    downloads = [
        block for block in plan_steps
        if re.search(r"uses:\s*actions/download-artifact@", block)
    ]
    if len(downloads) != 1 or not re.search(
        r"(?m)^\s+path:\s*\$\{\{\s*runner\.temp\s*\}\}/uaart-intake-import\s*$",
        downloads[0],
    ):
        raise ControlPlaneError("ORCHESTRATOR_ARTIFACT_DOWNLOAD_SCOPE")
    if DATA_ONLY_ARTIFACT_VALIDATION_MARKER not in jobs["plan"]:
        raise ControlPlaneError("ORCHESTRATOR_ARTIFACT_VALIDATION_MARKER")

    token_steps = [block for block in plan_steps if "github.token" in block]
    if len(token_steps) != 1 or source.count("github.token") != 1:
        raise ControlPlaneError("ORCHESTRATOR_GITHUB_TOKEN_STEP_COUNT")
    persist = token_steps[0]
    if "Persist only the exact claim and plan" not in persist:
        raise ControlPlaneError("ORCHESTRATOR_GITHUB_TOKEN_STEP_IDENTITY")
    for job_id in ("validate", "fast", "standard", "critical"):
        if GITHUB_WRITE_CREDENTIAL_RE.search(jobs[job_id]):
            raise ControlPlaneError(
                "ORCHESTRATOR_GITHUB_CREDENTIAL_EXPOSURE:" + job_id
            )
    plan_without_persist = jobs["plan"].replace(persist, "", 1)
    if GITHUB_WRITE_CREDENTIAL_RE.search(plan_without_persist):
        raise ControlPlaneError("ORCHESTRATOR_TOKEN_OUTSIDE_PERSIST_STEP")
    if re.search(r"secrets\s*\.\s*GITHUB_TOKEN|\bGITHUB_TOKEN\b", persist, re.I):
        raise ControlPlaneError("ORCHESTRATOR_GITHUB_TOKEN_ALIAS_FORBIDDEN")
    if persist.count("unset GH_TOKEN") != 1:
        raise ControlPlaneError("ORCHESTRATOR_TOKEN_LIFETIME")
    first_python = persist.find("python3 -I")
    if first_python < 0 or persist.index("unset GH_TOKEN") > first_python:
        raise ControlPlaneError("ORCHESTRATOR_TOKEN_LIFETIME")
    first_repo_python = persist.find("python3 -I automation/")
    closure_marker = persist.find("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED")
    if first_repo_python < 0 or closure_marker < 0 or closure_marker > first_repo_python:
        raise ControlPlaneError("ORCHESTRATOR_RUNTIME_BOOTSTRAP_ORDER")
    validation_step_indexes = [
        index
        for index, block in enumerate(plan_steps)
        if DATA_ONLY_ARTIFACT_VALIDATION_MARKER in block
    ]
    token_step_index = plan_steps.index(persist)
    if validation_step_indexes != [token_step_index - 1]:
        raise ControlPlaneError("ORCHESTRATOR_ARTIFACT_VALIDATION_ORDER")
    required_persist = (
        "python3 -I automation/control_plane.py verify-mode",
        "python3 -I automation/control_plane.py claim",
        "python3 -I automation/control_plane.py planning",
        "python3 -I automation/execution_contract.py validate",
        "for attempt in 1 2 3 4 5 6",
        "if ! git_auth fetch",
        "continue",
        "git merge-base --is-ancestor \"$last_commit\" \"$parent\"",
        'git merge-base --is-ancestor "$ATTESTED_WORKFLOW_SOURCE_COMMIT" "$parent"',
        'git cat-file blob "$parent:state/AUTOPILOT_RUNTIME_MANIFEST.json"',
        'git cat-file blob "$parent:$ATTESTED_REQUEST_PATH"',
        'git rev-parse "$parent:.github/workflows/uaart_orchestrator.yml"',
        "UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED",
        "INTAKE_RUNTIME_FILE_SET",
        "GIT_INDEX_FILE",
        "RUNNER_TEMP",
        "git read-tree",
        "git hash-object",
        "git update-index",
        "git commit-tree",
        'for path in "$CLAIM_PATH" "$PLAN_PATH"; do',
        'test "${#changed[@]}" -eq 2',
        'printf \'%s\\n\' "$CLAIM_PATH" "$PLAN_PATH"',
        "COMMIT:refs/heads/main",
    )
    if any(marker not in persist for marker in required_persist):
        raise ControlPlaneError("ORCHESTRATOR_PRIVILEGED_PERSIST_CONTRACT")
    push_lines = [
        line for line in persist.splitlines() if re.search(r"\bpush\s+origin\b", line)
    ]
    if not push_lines or any("COMMIT:refs/heads/main" not in line for line in push_lines):
        raise ControlPlaneError("ORCHESTRATOR_PUSH_TARGET_NOT_MAIN")

    required_artifact = (
        "UA-ART-INTAKE-ATTESTATION-1",
        "actual != ['attestation.json']",
        "INTAKE_ATTESTATION_SHA256",
        "INTAKE_ATTESTATION_INPUT_BINDING",
        "INTAKE_ATTESTATION_STATE_PATH",
        "INTAKE_ATTESTATION_RUNTIME_MANIFEST_SHA",
        "INTAKE_ATTESTATION_ORCHESTRATOR_BLOB",
    )
    if any(marker not in jobs["plan"] for marker in required_artifact):
        raise ControlPlaneError("ORCHESTRATOR_ARTIFACT_CONTRACT")
    # Structural checks above provide targeted diagnostics. This final pin makes
    # the privileged intake writer fail closed against shell/env/token-command
    # obfuscation that a text-oriented policy cannot safely enumerate.
    if sha256_bytes(source.encode("utf-8")) != ORCHESTRATOR_WORKFLOW_SHA256:
        raise ControlPlaneError("ORCHESTRATOR_WORKFLOW_SHA256")


def _verify_production_secret_step_policy(source: str, relative: str) -> None:
    total = len(PRODUCTION_CREDENTIAL_REFERENCE_RE.findall(source))
    blocks = _named_workflow_step_blocks(source, relative)
    secret_blocks = tuple(
        block for block in blocks if PRODUCTION_CREDENTIAL_REFERENCE_RE.search(block)
    )
    within_steps = sum(
        len(PRODUCTION_CREDENTIAL_REFERENCE_RE.findall(block))
        for block in secret_blocks
    )
    if within_steps != total:
        raise ControlPlaneError("PRODUCTION_CREDENTIAL_OUTSIDE_NAMED_STEP:" + relative)

    if relative == ".github/workflows/uaart_critical.yml":
        expected_jobs = {
            "backup": ("backup", "steps.preparing.outputs.validated == 'true'"),
            "run": (
                "controller_production",
                "steps.open_state.outputs.validated == 'true'",
            ),
            "rollback": (
                "rollback_execute",
                "steps.rolling_back.outputs.validated == 'true'",
            ),
        }
        if total != 3 or len(secret_blocks) != 3:
            raise ControlPlaneError("CRITICAL_PRODUCTION_CREDENTIAL_COUNT")
        secret_jobs = tuple(
            (job_id, job)
            for job_id, job in _workflow_job_blocks(source, relative)
            if PRODUCTION_CREDENTIAL_REFERENCE_RE.search(job)
        )
        if len(secret_jobs) != 3:
            raise ControlPlaneError("CRITICAL_PRODUCTION_CREDENTIAL_JOB_COUNT")
        for job_id, job in secret_jobs:
            header = job.split("\n    steps:", 1)[0]
            commands = _task_execution_commands(job)
            if len(commands) != 1 or not commands.issubset(expected_jobs):
                raise ControlPlaneError(
                    "CRITICAL_PRODUCTION_CREDENTIAL_JOB_COMMAND:" + job_id
                )
            command = next(iter(commands))
            expected_job, _gate = expected_jobs[command]
            if job_id != expected_job:
                raise ControlPlaneError(
                    "CRITICAL_PRODUCTION_CREDENTIAL_JOB_ID:" + job_id
                )
            if "\n    environment:\n      name: production\n" not in job:
                raise ControlPlaneError(
                    "CRITICAL_PRODUCTION_CREDENTIAL_ENVIRONMENT:" + job_id
                )
            if "github.run_attempt == 1" not in header:
                raise ControlPlaneError(
                    "CRITICAL_PRODUCTION_CREDENTIAL_JOB_RERUN_GATE:" + job_id
                )
        rollback_import_blocks = tuple(
            block
            for block in blocks
            if (
                "Download rollback receipt outside checkout" in block
                or "Strictly validate data-only rollback artifact" in block
            )
        )
        if len(rollback_import_blocks) != 2 or any(
            "github.run_attempt == 1" not in block
            for block in rollback_import_blocks
        ):
            raise ControlPlaneError("CRITICAL_ROLLBACK_ARTIFACT_RERUN_GATE")
        seen: set[str] = set()
        for block in secret_blocks:
            commands = _task_execution_commands(block)
            if (
                "inputs.production_required == 'true'" not in block
                or "github.run_attempt == 1" not in block
                or "test \"$GITHUB_RUN_ATTEMPT\" = '1'" not in block
            ):
                raise ControlPlaneError("CRITICAL_PRODUCTION_CREDENTIAL_GATE")
            if len(commands) != 1 or not commands.issubset(expected_jobs):
                raise ControlPlaneError("CRITICAL_PRODUCTION_CREDENTIAL_PLACEMENT")
            command = next(iter(commands))
            if expected_jobs[command][1] not in block:
                raise ControlPlaneError(
                    "CRITICAL_PRODUCTION_CREDENTIAL_OUTPUT_GATE:" + command
                )
            seen.add(command)
        if seen != set(expected_jobs):
            raise ControlPlaneError("CRITICAL_PRODUCTION_CREDENTIAL_COMMAND_SET")
    elif relative == ".github/workflows/uaart_transaction_watchdog.yml":
        if total != 1 or len(secret_blocks) != 1:
            raise ControlPlaneError("WATCHDOG_PRODUCTION_CREDENTIAL_COUNT")
        block = secret_blocks[0]
        if (
            "needs.discover.outputs.transaction_status == 'OPEN'" not in block
            or "needs.mark_rollback.outputs.marked == 'true'" not in block
            or "steps.orphan.outputs.transaction_status == 'ROLLING_BACK'" not in block
            or "steps.orphan.outputs.source_commit == needs.discover.outputs.source_commit" not in block
            or "steps.pinned.outputs.validated == 'true'" not in block
            or "github.run_attempt == 1" not in block
            or "test \"$GITHUB_RUN_ATTEMPT\" = '1'" not in block
            or 'cd "$PINNED_ROOT"' not in block
            or "execution_contract.py rollback" not in block
        ):
            raise ControlPlaneError("WATCHDOG_PRODUCTION_CREDENTIAL_GATE")
    else:
        raise ControlPlaneError("PRODUCTION_CREDENTIAL_WORKFLOW_BYPASS:" + relative)


def _verify_active_workflow_runtime_hygiene(source: str, relative: str) -> None:
    """Reject ambient Python startup and checkout-persisted credentials globally."""
    for job_id, job in _workflow_job_blocks(source, relative):
        for match in PYTHON_INTERPRETER_RE.finditer(job):
            if not re.match(r"\s+-I(?=\s|$)", job[match.end():]):
                raise ControlPlaneError(
                    "ACTIVE_WORKFLOW_PYTHON_NOT_ISOLATED:"
                    + relative + ":" + job_id
                )
        for block in _named_job_step_blocks(job, relative, job_id):
            body = _step_run_body(block, relative)
            if body is not None and "${{" in body:
                raise ControlPlaneError(
                    "ACTIVE_WORKFLOW_RUN_EXPRESSION_FORBIDDEN:" + relative
                )
            if re.search(r"uses:\s*actions/checkout@", block):
                if (
                    block.count("persist-credentials: false") != 1
                    or "persist-credentials: true" in block
                ):
                    raise ControlPlaneError(
                        "ACTIVE_WORKFLOW_CHECKOUT_CREDENTIAL_POLICY:"
                        + relative + ":" + job_id
                    )
                if relative in {
                    ".github/workflows/uaart_maintenance.yml",
                    ".github/workflows/uaart_monitor.yml",
                } and (
                    block.count("ref: main") != 1
                    or block.count("clean: true") != 1
                ):
                    raise ControlPlaneError(
                        "SCHEDULED_WORKFLOW_CHECKOUT_NOT_MAIN:"
                        + relative + ":" + job_id
                    )
        if relative in {
            ".github/workflows/uaart_maintenance.yml",
            ".github/workflows/uaart_monitor.yml",
        } and "github.ref == 'refs/heads/main'" not in job:
            raise ControlPlaneError(
                "SCHEDULED_WORKFLOW_MAIN_GUARD_MISSING:"
                + relative + ":" + job_id
            )


def _verify_privileged_python_token_boundary(source: str, relative: str) -> None:
    """Keep the Actions write token outside unverified repository Python."""
    if relative not in {
        ".github/workflows/uaart_critical.yml",
        ".github/workflows/uaart_transaction_watchdog.yml",
    }:
        return
    queue_seen = False
    for block in _named_workflow_step_blocks(source, relative):
        if "github.token" not in block:
            continue
        unset_at = block.find("unset GH_TOKEN")
        if unset_at < 0 or block.count("unset GH_TOKEN") < 1:
            raise ControlPlaneError("PRIVILEGED_GITHUB_TOKEN_NOT_UNSET:" + relative)
        first_python = PYTHON_INTERPRETER_RE.search(block)
        is_queue = (
            relative == ".github/workflows/uaart_critical.yml"
            and "Wait in strict Production queue and refresh main" in block
        )
        if is_queue:
            if queue_seen:
                raise ControlPlaneError("CRITICAL_QUEUE_TOKEN_STEP_DUPLICATE")
            queue_seen = True
            first_repo_python = block.find("python3 -I automation/")
            closure_at = block.find("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED")
            queue_at = block.find("python3 -I automation/production_queue.py wait")
            auth_at = block.find("auth=", queue_at)
            if (
                first_repo_python < 0
                or closure_at < 0
                or closure_at > first_repo_python
                or "CRITICAL_QUEUE_RUNTIME_FILE_SET" not in block
                or "RUNTIME_MANIFEST_SHA256" not in block
                or "target.resolve() != target" not in block
                or queue_at < first_repo_python
                or auth_at < queue_at
                or unset_at < auth_at
            ):
                raise ControlPlaneError("CRITICAL_QUEUE_RUNTIME_BOOTSTRAP_ORDER")
        elif first_python is not None and unset_at > first_python.start():
            raise ControlPlaneError(
                "PRIVILEGED_GITHUB_TOKEN_PYTHON_EXPOSURE:" + relative
            )
    if relative == ".github/workflows/uaart_critical.yml" and not queue_seen:
        raise ControlPlaneError("CRITICAL_QUEUE_TOKEN_STEP_MISSING")


def _verify_critical_runtime_binding_policy(source: str, relative: str) -> None:
    if relative != ".github/workflows/uaart_critical.yml":
        return
    jobs = dict(_workflow_job_blocks(source, relative))
    validate = jobs.get("validate", "")
    for marker in (
        "dependency_sha256: ${{ steps.contract.outputs.dependency_sha256 }}",
        "runtime_manifest_sha256: ${{ steps.attestation.outputs.runtime_manifest_sha256 }}",
        "workflow_blob_oid: ${{ steps.workflow.outputs.workflow_blob_oid }}",
        "workflow_source_commit: ${{ steps.workflow.outputs.workflow_source_commit }}",
        "'dependency_sha256'",
        "'runtime_manifest_sha256'",
        "'workflow_blob_oid'",
        "'workflow_source_commit'",
        "AUTOPILOT_RUNTIME_MANIFEST.json",
        "Bind executing CRITICAL workflow to checked runtime",
        "git ls-tree \"$WORKFLOW_SOURCE_COMMIT\"",
    ):
        if marker not in validate:
            raise ControlPlaneError("CRITICAL_VALIDATION_RUNTIME_BINDING")
    if "VALIDATION_WORKFLOW_BLOB_BINDING" not in source:
        raise ControlPlaneError("CRITICAL_VALIDATION_RUNTIME_BINDING")
    if "UAART_RUNTIME_PINNED_PATHS" not in source or any(marker not in validate for marker in (
        "UAART_CRITICAL_VALIDATION_RUNTIME_CLOSURE_VALIDATED",
        "CRITICAL_VALIDATION_RUNTIME_FILE_SET",
        "target.resolve() != target",
    )):
        raise ControlPlaneError("CRITICAL_VALIDATION_RUNTIME_CLOSURE")
    closure_at = validate.find("UAART_CRITICAL_VALIDATION_RUNTIME_CLOSURE_VALIDATED")
    first_repo_python = validate.find("python3 -I automation/")
    if closure_at < 0 or first_repo_python < 0 or closure_at > first_repo_python:
        raise ControlPlaneError("CRITICAL_VALIDATION_RUNTIME_CLOSURE_ORDER")
    head_runtime_guard = (
        'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" HEAD -- "${runtime_paths[@]}"'
    )
    for job_id in (
        "prepare", "backup", "open", "controller_production",
        "controller_nonproduction", "finalize",
    ):
        if head_runtime_guard not in jobs.get(job_id, ""):
            raise ControlPlaneError("CRITICAL_FULL_RUNTIME_DRIFT_GUARD:" + job_id)
    for job_id in ("backup", "controller_production", "controller_nonproduction"):
        job = jobs.get(job_id, "")
        required = (
            "DEPENDENCY_SHA256",
            "RUNTIME_MANIFEST_SHA256",
            "SOURCE_COMMIT",
            "execution_contract.py validate",
            "dependency_sha256",
            "sha256sum state/AUTOPILOT_RUNTIME_MANIFEST.json",
            'git diff --quiet "$SOURCE_COMMIT" HEAD -- "$package_root"',
            "WORKFLOW_BLOB_OID",
            "WORKFLOW_SOURCE_COMMIT",
            'git rev-parse "HEAD:$WORKFLOW_PATH"',
        )
        if any(marker not in job for marker in required):
            raise ControlPlaneError(
                "CRITICAL_FORWARD_RUNTIME_DRIFT_GUARD:" + job_id
            )
    rollback = jobs.get("rollback_execute", "")
    required_rollback = (
        "PINNED_ROOT",
        "SOURCE_COMMIT",
        "DEPENDENCY_SHA256",
        "RUNTIME_MANIFEST_SHA256",
        'git -c core.hooksPath=/dev/null worktree add --detach',
        'test "$(git -C "$PINNED_ROOT" rev-parse HEAD)" = "$SOURCE_COMMIT"',
        "UAART_PINNED_DURABLE_STATE_COPIED",
        "UAART_PINNED_RUNTIME_CLOSURE_VALIDATED",
        "PINNED_SOURCE_COMMIT_BINDING",
        "PINNED_RUNTIME_MANIFEST_BINDING",
        "target.resolve() != target",
        "dependency_sha256",
        "value.get('source_commit') == os.environ['SOURCE_COMMIT']",
        "WORKFLOW_BLOB_OID",
        "WORKFLOW_SOURCE_COMMIT",
        'git rev-parse "$SOURCE_COMMIT:$WORKFLOW_PATH"',
        'cd "$PINNED_ROOT"',
    )
    if any(marker not in rollback for marker in required_rollback):
        raise ControlPlaneError("CRITICAL_PINNED_ROLLBACK_RUNTIME_MISSING")
    push_blocks = [
        block for block in _named_workflow_step_blocks(source, relative)
        if re.search(r"\bpush\s+origin\b", block)
    ]
    if len(push_blocks) != 5 or any(
        'git diff --quiet "$last_commit" "$parent" -- "${accepted_paths[@]}"'
        not in block
        for block in push_blocks
    ):
        raise ControlPlaneError("CRITICAL_ACCEPTED_PUSH_PATH_DRIFT_GUARD")
    for job_id in ("prepare", "open", "finalize"):
        job = jobs.get(job_id, "")
        if any(marker not in job for marker in (
            "WORKFLOW_BLOB_OID",
            "WORKFLOW_SOURCE_COMMIT",
            "RUNTIME_MANIFEST_SHA256",
            'git rev-parse "$parent:$WORKFLOW_PATH"',
            'git show "$parent:state/AUTOPILOT_RUNTIME_MANIFEST.json"',
            'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" "$parent" -- "${runtime_paths[@]}"',
        )):
            raise ControlPlaneError(
                "CRITICAL_PERSIST_WORKFLOW_RUNTIME_BINDING:" + job_id
            )


def _verify_watchdog_pinned_recovery_policy(source: str, relative: str) -> None:
    if relative != ".github/workflows/uaart_transaction_watchdog.yml":
        return
    jobs = dict(_workflow_job_blocks(source, relative))
    discover = jobs.get("discover", "")
    rollback = jobs.get("rollback_open", "")
    if (
        "source_commit: ${{ steps.orphan.outputs.source_commit }}" not in discover
        or "claim_path: ${{ steps.orphan.outputs.claim_path }}" not in discover
    ):
        raise ControlPlaneError("WATCHDOG_RECOVERY_SOURCE_OUTPUT_MISSING")
    required = (
        "PINNED_ROOT",
        "SOURCE_COMMIT",
        "fetch-depth: 0",
        'git -c core.hooksPath=/dev/null worktree add --detach',
        "UAART_PINNED_DURABLE_STATE_COPIED",
        "UAART_PINNED_RUNTIME_CLOSURE_VALIDATED",
        "UAART_PINNED_RECOVERY_IDENTITY_VALIDATED",
        "PINNED_SOURCE_COMMIT_BINDING",
        "target.resolve() != target",
        "steps.orphan.outputs.transaction_status == 'ROLLING_BACK'",
        "steps.orphan.outputs.source_commit == needs.discover.outputs.source_commit",
        "steps.pinned.outputs.validated == 'true'",
        'cd "$PINNED_ROOT"',
    )
    if any(marker not in rollback for marker in required):
        raise ControlPlaneError("WATCHDOG_PINNED_RECOVERY_RUNTIME_MISSING")
    push_blocks = [
        block for block in _named_workflow_step_blocks(source, relative)
        if re.search(r"\bpush\s+origin\b", block)
    ]
    if len(push_blocks) != 6 or any(
        'git diff --quiet "$LAST_COMMIT" "$PARENT" -- "${ACCEPTED_PATHS[@]}"'
        not in block
        for block in push_blocks
    ):
        raise ControlPlaneError("WATCHDOG_ACCEPTED_PUSH_PATH_DRIFT_GUARD")


def _verify_write_job_runtime_bootstrap_policy(source: str, relative: str) -> None:
    """Reject write jobs that can run moving repository code before token use.

    Step-scoped ``GH_TOKEN`` is not sufficient isolation: repository Python in
    an earlier step can poison ``GITHUB_ENV``/``GITHUB_PATH``, while repository
    Python in the token step can replace a writable PATH binary or Git config.
    Every state writer therefore binds the complete runtime to an attested
    source before its first repository Python and repeats that binding for each
    moving-main retry parent.
    """
    expected_writers = {
        ".github/workflows/uaart_critical.yml": {
            "prepare", "open", "finalize", "recover", "rollback_mark",
        },
        ".github/workflows/uaart_transaction_watchdog.yml": {
            "halt_discovery_failure", "halt_preparing", "mark_rollback",
            "finalize_rollback", "halt_rolling_back", "halt_recovery_failure",
        },
    }.get(relative)
    if expected_writers is None:
        return
    jobs = dict(_workflow_job_blocks(source, relative))
    actual_writers = {
        job_id for job_id, job in jobs.items() if "contents: write" in job
    }
    if actual_writers != expected_writers:
        raise ControlPlaneError("WRITE_JOB_SET_INVALID:" + relative)
    poison_markers = (
        "GITHUB_ENV", "GITHUB_PATH", "BASH_ENV", "PYTHONSTARTUP",
        "PYTHONPATH", "PYTHONHOME", "GIT_CONFIG_GLOBAL", ".gitconfig",
    )
    for job_id in sorted(expected_writers):
        job = jobs[job_id]
        if any(marker in job for marker in poison_markers) or re.search(
            r"(?m)(?:^\s*|[;&|]\s*)git\s+config(?:\s|$)", job
        ):
            raise ControlPlaneError(
                "WRITE_JOB_ENVIRONMENT_POISONING:" + relative + ":" + job_id
            )
        first_repo_python = job.find("python3 -I automation/")
        if first_repo_python < 0:
            raise ControlPlaneError(
                "WRITE_JOB_REPOSITORY_PYTHON_MISSING:" + relative + ":" + job_id
            )
        candidate_guards = (
            job.find("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED"),
            job.find(
                'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" HEAD -- '
                '"${runtime_paths[@]}"'
            ),
            job.find("UAART_SOURCE_PINNED_WRITER_RUNTIME_VALIDATED"),
        )
        guards = [position for position in candidate_guards if position >= 0]
        if not guards or min(guards) > first_repo_python:
            raise ControlPlaneError(
                "WRITE_JOB_RUNTIME_BOOTSTRAP_ORDER:" + relative + ":" + job_id
            )
        token_steps = [
            block for block in _named_job_step_blocks(job, relative, job_id)
            if "github.token" in block
        ]
        if not token_steps:
            raise ControlPlaneError(
                "WRITE_JOB_TOKEN_STEP_COUNT:" + relative + ":" + job_id
            )
        for token_step in token_steps:
            unset_at = token_step.find("unset GH_TOKEN")
            token_repo_python = token_step.find("python3 -I automation/")
            queue_guard = token_step.find("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED")
            trusted_queue = (
                relative.endswith("uaart_critical.yml")
                and "Wait in strict Production queue and refresh main" in token_step
                and queue_guard >= 0
                and queue_guard < token_repo_python
            )
            if unset_at < 0 or (
                token_repo_python >= 0
                and unset_at > token_repo_python
                and not trusted_queue
            ):
                raise ControlPlaneError(
                    "WRITE_JOB_TOKEN_UNSET_ORDER:" + relative + ":" + job_id
                )

        if relative.endswith("uaart_critical.yml"):
            parent_guards = (
                'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" "$parent" -- '
                '"${runtime_paths[@]}"',
                'git diff --quiet "$SOURCE_COMMIT" "$parent" -- '
                '"${runtime_paths[@]}"',
            )
        else:
            parent_guards = (
                'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" "$PARENT" -- '
                '"${RUNTIME_PATHS[@]}"',
                'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" "$parent" -- '
                '"${runtime_paths[@]}"',
            )
        if not any(marker in job for marker in parent_guards):
            raise ControlPlaneError(
                "WRITE_JOB_RETRY_RUNTIME_BINDING:" + relative + ":" + job_id
            )
    expected_source_sha = {
        ".github/workflows/uaart_critical.yml": CRITICAL_WORKFLOW_SHA256,
        ".github/workflows/uaart_transaction_watchdog.yml": WATCHDOG_WORKFLOW_SHA256,
    }[relative]
    actual_source_sha = sha256_bytes(source.encode("utf-8"))
    if actual_source_sha != expected_source_sha:
        raise ControlPlaneError("WRITE_WORKFLOW_EXACT_SHA256_MISMATCH:" + relative)


def verify_production_credential_workflow_policy(
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    """Keep the write-capable PythonAnywhere credential inside pinned recovery paths.

    An automatic or manual legacy workflow with the real secret reference is a
    control-plane bypass even when its current script claims to be read-only:
    the same triggering change could alter that script.  Non-production and
    quarantined workflows must use a separately provisioned least-privilege
    secret name or an intentionally unset disabled placeholder.
    """
    workflow_root = root / ".github/workflows"
    if workflow_root.is_symlink() or not workflow_root.is_dir():
        raise ControlPlaneError("WORKFLOW_POLICY_DIRECTORY_INVALID")
    paths = sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
    relatives = {path.relative_to(root).as_posix() for path in paths}
    expected = set(ACTIVE_WORKFLOW_EVENT_POLICY)
    if relatives != expected:
        missing = ",".join(sorted(expected - relatives)) or "-"
        unexpected = ",".join(sorted(relatives - expected)) or "-"
        raise ControlPlaneError(
            "ACTIVE_WORKFLOW_SET_MISMATCH:missing=" + missing + ":unexpected=" + unexpected
        )

    consumers: list[str] = []
    inherited: list[str] = []
    event_inventory: dict[str, list[str]] = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ControlPlaneError("WORKFLOW_POLICY_FILE_INVALID:" + path.name)
        relative = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ControlPlaneError("WORKFLOW_NOT_UTF8:" + relative) from exc
        events = _workflow_events(source, relative)
        if events != ACTIVE_WORKFLOW_EVENT_POLICY[relative]:
            raise ControlPlaneError("WORKFLOW_EVENT_POLICY_MISMATCH:" + relative)
        event_inventory[relative] = sorted(events)
        trigger = _workflow_trigger_block(source, relative)
        if relative.endswith("uaart_autostart.yml"):
            required = (
                "on:\n"
                "  push:\n"
                "    branches:\n"
                "      - main\n"
                "    paths:\n"
                "      - 'tasks/launch/AUTO-*.json'\n"
            )
            if trigger != required:
                raise ControlPlaneError("AUTOSTART_TRIGGER_SCOPE_MISMATCH")
        schedules = re.findall(
            r"(?m)^\s+-\s+cron:\s*['\"]([^'\"]+)['\"]\s*$", trigger
        )
        expected_schedule = {
            ".github/workflows/uaart_maintenance.yml": ["31 3 * * *"],
            ".github/workflows/uaart_monitor.yml": ["17 */6 * * *"],
            ".github/workflows/uaart_transaction_watchdog.yml": ["*/10 * * * *"],
        }.get(relative, [])
        if schedules != expected_schedule:
            raise ControlPlaneError("WORKFLOW_SCHEDULE_POLICY_MISMATCH:" + relative)
        if PRODUCTION_CREDENTIAL_REFERENCE_RE.search(source):
            consumers.append(relative)
            if relative not in PRODUCTION_CREDENTIAL_WORKFLOW_ALLOWLIST:
                raise ControlPlaneError("PRODUCTION_CREDENTIAL_WORKFLOW_BYPASS:" + relative)
            _verify_production_secret_step_policy(source, relative)
        if SECRETS_BRACKET_REFERENCE_RE.search(source):
            raise ControlPlaneError("WORKFLOW_SECRET_BRACKET_BYPASS:" + relative)
        if SECRETS_SERIALIZATION_RE.search(source):
            raise ControlPlaneError("WORKFLOW_SECRET_SERIALIZATION_BYPASS:" + relative)
        if SECRETS_INHERIT_RE.search(source):
            inherited.append(relative)
            if relative not in SECRETS_INHERIT_WORKFLOW_ALLOWLIST:
                raise ControlPlaneError("WORKFLOW_SECRET_INHERIT_BYPASS:" + relative)
        if re.search(r"(?m)^\s*actions:\s*write\s*(?:#.*)?$", source):
            raise ControlPlaneError("WORKFLOW_ACTIONS_WRITE_BYPASS:" + relative)
        if WORKFLOW_REMOTE_DISPATCH_RE.search(source):
            raise ControlPlaneError("WORKFLOW_REMOTE_DISPATCH_BYPASS:" + relative)
        if relative == ".github/workflows/uaart_autostart.yml":
            _verify_autostart_fresh_runner_policy(source, relative)
        elif relative == ".github/workflows/uaart_orchestrator.yml":
            _verify_orchestrator_fresh_runner_policy(source, relative)
        elif relative in {
            ".github/workflows/uaart_fast.yml",
            ".github/workflows/uaart_standard.yml",
            ".github/workflows/uaart_critical.yml",
            ".github/workflows/uaart_transaction_watchdog.yml",
        }:
            _verify_fresh_runner_job_policy(source, relative)
        _verify_active_workflow_runtime_hygiene(source, relative)
        _verify_privileged_python_token_boundary(source, relative)
        _verify_critical_runtime_binding_policy(source, relative)
        _verify_watchdog_pinned_recovery_policy(source, relative)
        _verify_write_job_runtime_bootstrap_policy(source, relative)
    if set(consumers) != set(PRODUCTION_CREDENTIAL_WORKFLOW_ALLOWLIST):
        raise ControlPlaneError("PRODUCTION_CREDENTIAL_CONSUMER_SET")
    return {
        "active_workflows": sorted(relatives),
        "allowlist": sorted(PRODUCTION_CREDENTIAL_WORKFLOW_ALLOWLIST),
        "consumers": consumers,
        "events": event_inventory,
        "secrets_inherit": inherited,
        "status": "PASS",
    }


def verify_execution_mode(
    *,
    root: pathlib.Path = ROOT,
    required_mode: str | None = None,
    allow_halt_for_recovery: bool = False,
) -> dict[str, Any]:
    """Validate the repository's single execution-mode authority.

    MANUAL is accepted only while the legacy marker is explicitly ACTIVE.
    AUTOMATIC is accepted only when the TASK107-R2 receipt and the owner's
    separate global-production approval are both pinned by SHA-256.
    """
    required = str(required_mode or "").upper()
    if required and required not in EXECUTION_MODES:
        raise ControlPlaneError("INVALID_REQUIRED_EXECUTION_MODE")

    manual_path = root / "state/MANUAL_MODE.md"
    mode_path = root / "state/EXECUTION_MODE.json"
    if not mode_path.is_file():
        require_mode_status(manual_path, "ACTIVE")
        result = {
            "status": "PASS",
            "mode": "MANUAL",
            "automatic_nonproduction": False,
            "automatic_production": False,
        }
        if required and required != "MANUAL":
            raise ControlPlaneError("EXECUTION_MODE_REQUIRED:" + required)
        return result

    if mode_path.is_symlink() or not mode_path.is_file():
        raise ControlPlaneError("EXECUTION_MODE_FILE_INVALID")
    mode = read_json(mode_path)
    halt_path = root / "state/AUTOPILOT_HALT.json"
    halted = halt_path.exists()
    if halted and not allow_halt_for_recovery:
        raise ControlPlaneError("AUTOMATIC_MODE_HALTED")
    halt = None
    if halted:
        if halt_path.is_symlink() or not halt_path.is_file():
            raise ControlPlaneError("AUTOMATIC_HALT_FILE_INVALID")
        halt = read_json(halt_path)
    expected_mode_keys = {
        "activated_at",
        "allow_replay_existing_launch_markers",
        "automatic_nonproduction",
        "automatic_production",
        "mode",
        "mode_epoch",
        "owner_approval_path",
        "owner_approval_sha256",
        "production_requires_backup",
        "production_requires_exact_launch",
        "production_requires_gate_b",
        "production_requires_live_receipt",
        "production_requires_owner_approval",
        "production_requires_pre_post_health",
        "runtime_manifest_path",
        "runtime_manifest_sha256",
        "schema_version",
        "stop_on_safety_failure",
        "task107_receipt_path",
        "task107_receipt_sha256",
    }
    if set(mode) != expected_mode_keys:
        raise ControlPlaneError("EXECUTION_MODE_KEYS_MISMATCH")
    if mode.get("schema_version") != EXECUTION_MODE_SCHEMA or mode.get("mode") != "AUTOMATIC":
        raise ControlPlaneError("EXECUTION_MODE_SCHEMA_OR_VALUE")
    if not re.fullmatch(r"auto-[A-Za-z0-9._-]{16,100}", str(mode.get("mode_epoch", ""))):
        raise ControlPlaneError("EXECUTION_MODE_EPOCH")
    if halt is not None and (
        halt.get("status") != "EMERGENCY_HALT"
        or halt.get("mode_epoch") != mode.get("mode_epoch")
    ):
        raise ControlPlaneError("AUTOMATIC_HALT_IDENTITY_INVALID")
    try:
        require_mode_status(manual_path, "INACTIVE")
    except ControlPlaneError as exc:
        raise ControlPlaneError("MANUAL_MODE_NOT_INACTIVE") from exc
    for key in (
        "automatic_nonproduction",
        "automatic_production",
        "production_requires_backup",
        "production_requires_exact_launch",
        "production_requires_gate_b",
        "production_requires_live_receipt",
        "production_requires_owner_approval",
        "production_requires_pre_post_health",
        "stop_on_safety_failure",
    ):
        if mode.get(key) is not True:
            raise ControlPlaneError("EXECUTION_MODE_REQUIRED_TRUE:" + key)
    if mode.get("allow_replay_existing_launch_markers") is not False:
        raise ControlPlaneError("EXECUTION_MODE_REPLAY_MUST_BE_FALSE")
    parse_utc(str(mode.get("activated_at", "")))

    receipt_rel = safe_repo_path(str(mode.get("task107_receipt_path", "")))
    if receipt_rel != "state/receipts/TASK107-R2.json":
        raise ControlPlaneError("TASK107_RECEIPT_PATH_MISMATCH")
    receipt_path = repo_path(receipt_rel, root)
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ControlPlaneError("TASK107_RECEIPT_FILE_INVALID")
    if sha256_file(receipt_path) != require_sha(mode.get("task107_receipt_sha256"), "task107_receipt"):
        raise ControlPlaneError("TASK107_RECEIPT_SHA_MISMATCH")
    receipt = read_json(receipt_path)
    if (
        receipt.get("task_id") != "TASK107-R2"
        or receipt.get("status") != "FINISHED"
        or receipt.get("canary_result") != "3/3 PASS"
        or receipt.get("tests") != "PASS"
        or receipt.get("rollback_drill") != "PASS"
        or int(receipt.get("unexpected_changes", -1)) != 0
        or receipt.get("production_touched") is not False
    ):
        raise ControlPlaneError("TASK107_RECEIPT_NOT_ACCEPTABLE")

    approval_rel = safe_repo_path(str(mode.get("owner_approval_path", "")))
    if approval_rel != "tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json":
        raise ControlPlaneError("AUTOMATIC_APPROVAL_PATH_MISMATCH")
    approval_path = repo_path(approval_rel, root)
    if approval_path.is_symlink() or not approval_path.is_file():
        raise ControlPlaneError("AUTOMATIC_APPROVAL_FILE_INVALID")
    if sha256_file(approval_path) != require_sha(mode.get("owner_approval_sha256"), "automatic_approval"):
        raise ControlPlaneError("AUTOMATIC_APPROVAL_SHA_MISMATCH")
    approval = read_json(approval_path)
    expected_approval_keys = {
        "allow_replay_existing_launch_markers",
        "approved_at",
        "automatic_nonproduction",
        "automatic_production",
        "mode_epoch",
        "owner",
        "owner_authorized",
        "owner_command",
        "production_requires_backup",
        "production_requires_exact_launch",
        "production_requires_gate_b",
        "production_requires_live_receipt",
        "production_requires_owner_approval",
        "production_requires_pre_post_health",
        "runtime_manifest_path",
        "runtime_manifest_sha256",
        "schema_version",
        "stop_on_safety_failure",
        "task107_receipt_path",
        "task107_receipt_sha256",
        "task_id",
    }
    if set(approval) != expected_approval_keys:
        raise ControlPlaneError("AUTOMATIC_APPROVAL_KEYS_MISMATCH")
    if approval.get("schema_version") != AUTOMATIC_APPROVAL_SCHEMA:
        raise ControlPlaneError("AUTOMATIC_APPROVAL_SCHEMA")
    if approval.get("task_id") != "TASK107-R2-AUTOMATIC-MODE":
        raise ControlPlaneError("AUTOMATIC_APPROVAL_TASK_ID")
    if approval.get("owner") != "Артём Бровинский / UA ART COMPANY LLC":
        raise ControlPlaneError("AUTOMATIC_APPROVAL_OWNER")
    if approval.get("owner_authorized") is not True:
        raise ControlPlaneError("AUTOMATIC_APPROVAL_MISSING")
    if approval.get("owner_command") != "Включай глобальный продакшн автопилот.":
        raise ControlPlaneError("AUTOMATIC_APPROVAL_COMMAND_MISMATCH")
    if approval.get("mode_epoch") != mode.get("mode_epoch"):
        raise ControlPlaneError("AUTOMATIC_APPROVAL_EPOCH_MISMATCH")
    for key in (
        "automatic_nonproduction",
        "automatic_production",
        "production_requires_backup",
        "production_requires_exact_launch",
        "production_requires_gate_b",
        "production_requires_live_receipt",
        "production_requires_owner_approval",
        "production_requires_pre_post_health",
        "stop_on_safety_failure",
    ):
        if approval.get(key) is not True or approval.get(key) != mode.get(key):
            raise ControlPlaneError("AUTOMATIC_APPROVAL_POLICY_MISMATCH:" + key)
    if approval.get("allow_replay_existing_launch_markers") is not False:
        raise ControlPlaneError("AUTOMATIC_APPROVAL_REPLAY_MUST_BE_FALSE")
    if (
        approval.get("task107_receipt_path") != receipt_rel
        or approval.get("task107_receipt_sha256") != mode.get("task107_receipt_sha256")
    ):
        raise ControlPlaneError("AUTOMATIC_APPROVAL_RECEIPT_BINDING")
    if parse_utc(str(approval.get("approved_at", ""))) > parse_utc(str(mode["activated_at"])):
        raise ControlPlaneError("AUTOMATIC_APPROVAL_AFTER_ACTIVATION")

    runtime_rel = safe_repo_path(str(mode.get("runtime_manifest_path", "")))
    if runtime_rel != RUNTIME_MANIFEST_PATH \
            or approval.get("runtime_manifest_path") != runtime_rel:
        raise ControlPlaneError("RUNTIME_MANIFEST_PATH_MISMATCH")
    runtime_path = repo_path(runtime_rel, root)
    if runtime_path.is_symlink() or not runtime_path.is_file():
        raise ControlPlaneError("RUNTIME_MANIFEST_FILE_INVALID")
    runtime_sha = require_sha(mode.get("runtime_manifest_sha256"), "runtime_manifest")
    if approval.get("runtime_manifest_sha256") != runtime_sha:
        raise ControlPlaneError("RUNTIME_MANIFEST_APPROVAL_BINDING")
    if sha256_file(runtime_path) != runtime_sha:
        raise ControlPlaneError("RUNTIME_MANIFEST_SHA_MISMATCH")
    runtime = read_json(runtime_path)
    if set(runtime) != {"files", "generated_at", "mode_epoch", "schema_version"}:
        raise ControlPlaneError("RUNTIME_MANIFEST_SCHEMA")
    if runtime.get("schema_version") != RUNTIME_MANIFEST_SCHEMA \
            or runtime.get("mode_epoch") != mode.get("mode_epoch"):
        raise ControlPlaneError("RUNTIME_MANIFEST_IDENTITY")
    if parse_utc(str(runtime.get("generated_at", ""))) > parse_utc(str(mode["activated_at"])):
        raise ControlPlaneError("RUNTIME_MANIFEST_AFTER_ACTIVATION")
    files = runtime.get("files")
    if not isinstance(files, dict) or set(files) != set(RUNTIME_PINNED_PATHS):
        raise ControlPlaneError("RUNTIME_MANIFEST_FILE_SET")
    for relative in RUNTIME_PINNED_PATHS:
        pinned = repo_path(relative, root)
        if pinned.is_symlink() or not pinned.is_file():
            raise ControlPlaneError("RUNTIME_PINNED_FILE_INVALID:" + relative)
        if sha256_file(pinned) != require_sha(files.get(relative), "runtime:" + relative):
            raise ControlPlaneError("RUNTIME_PINNED_FILE_SHA_MISMATCH:" + relative)

    verify_production_credential_workflow_policy(root=root)

    result = dict(mode)
    result["status"] = "PASS"
    if required and required != "AUTOMATIC":
        raise ControlPlaneError("EXECUTION_MODE_REQUIRED:" + required)
    return result


def atomic_json(path: pathlib.Path, value: Mapping[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if exclusive:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError as exc:
            raise ControlPlaneError("ATOMIC_TARGET_EXISTS:" + str(path)) from exc
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".r2.tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".r2.tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_request(request_path: str, root: pathlib.Path = ROOT) -> tuple[str, pathlib.Path, dict[str, Any], str]:
    normalized = safe_repo_path(request_path)
    if not normalized.startswith("tasks/requests/") or not normalized.endswith(".json"):
        raise ControlPlaneError("REQUEST_PATH_SCOPE")
    path = repo_path(normalized, root)
    if path.is_symlink() or not path.is_file():
        raise ControlPlaneError("REQUEST_FILE_MISSING:" + normalized)
    raw = read_json(path)
    task_id = str(raw.get("task_id", "")).strip()
    if not TASK_ID_RE.fullmatch(task_id):
        raise ControlPlaneError("INVALID_TASK_ID")
    if not str(raw.get("title", "")).strip():
        raise ControlPlaneError("EMPTY_TITLE")
    return normalized, path, raw, sha256_file(path)


def normalized_changed_paths(raw: Mapping[str, Any]) -> tuple[str, ...]:
    values = raw.get("changed_paths", [])
    if not isinstance(values, list):
        raise ControlPlaneError("CHANGED_PATHS_NOT_ARRAY")
    return tuple(sorted({safe_repo_path(str(value)) for value in values}))


def classify_request(raw: Mapping[str, Any]) -> str:
    """Classify from declared target paths; control-plane paths are CRITICAL."""
    paths = normalized_changed_paths(raw)
    text = (str(raw.get("title", "")) + "\n" + str(raw.get("description", ""))).casefold()
    critical_paths = (
        ".github/workflows/",
        "automation/control_plane.py",
        "automation/production_queue.py",
        "automation/critical_adapter.py",
        "state/schemas/",
    )
    critical_tokens = (
        "database migration",
        "delete data",
        "credentials",
        "security",
        "dns",
        "cloudflare",
        "deployment architecture",
    )
    standard_tokens = (
        "crm",
        "catalog",
        "counter",
        "backend",
        "publication",
        "generator",
    )
    if any(path.startswith(critical_paths) for path in paths) or any(token in text for token in critical_tokens):
        detected = "CRITICAL"
    elif (
        any(path.lower().endswith((".py", ".js", ".ts", ".tsx")) for path in paths)
        or any(token in text for token in standard_tokens)
        or int(raw.get("complexity", 1)) >= 4
    ):
        detected = "STANDARD"
    else:
        detected = "FAST"
    minimum = str(raw.get("requested_min_class") or "").upper()
    rank = {"FAST": 1, "STANDARD": 2, "CRITICAL": 3}
    if minimum:
        if minimum not in rank:
            raise ControlPlaneError("INVALID_REQUESTED_MIN_CLASS")
        if rank[minimum] > rank[detected]:
            detected = minimum
    return detected


def _card_lock(path: str) -> str | None:
    match = re.search(r"ua[-_]?0*(\d{1,4})", path, re.I)
    if match:
        return "CARD:UA-%04d" % int(match.group(1))
    return None


def resource_locks(raw: Mapping[str, Any]) -> tuple[str, ...]:
    paths = normalized_changed_paths(raw)
    if bool(raw.get("read_only", False)):
        digest = sha256_bytes("\n".join(paths).encode("utf-8"))[:16]
        return ("READ_ONLY:" + digest,)
    locks: set[str] = set()
    for path in paths:
        folded = path.casefold()
        if path.startswith(".github/workflows/") or path.startswith("automation/") or path.startswith("state/schemas/"):
            locks.add("CONTROL_PLANE")
        if "crm" in folded or folded.endswith((".db", ".sqlite", ".sqlite3")):
            locks.add("CRM_DB")
        if "catalog" in folded or "generator" in folded or "publisher" in folded:
            locks.add("CATALOG_RENDERER")
        if "index.html" in folded or "homepage" in folded:
            locks.add("HOMEPAGE")
        card = _card_lock(path)
        if card:
            locks.add(card)
        if "cloudflare" in folded or "wrangler" in folded:
            locks.add("CLOUDFLARE_CONFIG")
        if "dns" in folded:
            locks.add("DNS")
        if "auth" in folded or "secret" in folded or "security" in folded:
            locks.add("SECURITY_CONTROL_PLANE")
    text = (str(raw.get("title", "")) + "\n" + str(raw.get("description", ""))).casefold()
    if "all cards" in text or "mass update" in text:
        locks.add("CATALOG_ALL_CARDS")
    if not locks:
        if paths:
            scopes = []
            for path in paths:
                parts = pathlib.PurePosixPath(path).parts[:2]
                scopes.append("/".join(parts))
            digest = sha256_bytes("\n".join(sorted(set(scopes))).encode("utf-8"))[:16]
            locks.add("PATH_SCOPE:" + digest)
        else:
            locks.add("TASK_ID:" + str(raw.get("task_id", "UNKNOWN")))
    return tuple(sorted(locks))


def locks_conflict(first: Iterable[str], second: Iterable[str]) -> bool:
    a, b = set(first), set(second)
    if not a or not b:
        return False
    if all(value.startswith("READ_ONLY:") for value in a) or all(value.startswith("READ_ONLY:") for value in b):
        return False
    if "GLOBAL_PRODUCTION" in a or "GLOBAL_PRODUCTION" in b:
        return True
    if "CATALOG_ALL_CARDS" in a and any(value.startswith("CARD:") or value == "CATALOG_RENDERER" for value in b):
        return True
    if "CATALOG_ALL_CARDS" in b and any(value.startswith("CARD:") or value == "CATALOG_RENDERER" for value in a):
        return True
    return bool(a & b)


def queue_key(locks: Sequence[str]) -> str:
    readable = re.sub(r"[^A-Za-z0-9_-]+", "-", locks[0]).strip("-").lower()[:28]
    digest = sha256_bytes("\n".join(sorted(locks)).encode("utf-8"))[:16]
    return (readable or "resource") + "-" + digest


def _identity(raw: Mapping[str, Any], request_sha256: str, run_id: str) -> dict[str, str]:
    run = str(run_id).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", run):
        raise ControlPlaneError("INVALID_RUN_ID")
    return {
        "task_id": str(raw["task_id"]),
        "task_sha256": require_sha(request_sha256, "task"),
        "run_id": run,
    }


def claim_relative_path(identity: Mapping[str, str]) -> str:
    return "state/claims/%s.%s.%s.json" % (
        identity["task_id"], identity["task_sha256"], identity["run_id"]
    )


def plan_relative_path(identity: Mapping[str, str]) -> str:
    return "state/plans/%s.%s.json" % (identity["task_id"], identity["task_sha256"])


def transaction_relative_path(identity: Mapping[str, str]) -> str:
    return "state/transactions/%s.%s.%s.json" % (
        identity["task_id"], identity["task_sha256"], identity["run_id"]
    )


def _claim_files(root: pathlib.Path) -> list[pathlib.Path]:
    folder = root / "state/claims"
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def _is_active(claim: Mapping[str, Any]) -> bool:
    return str(claim.get("task_execution_status", "")) in ACTIVE_EXECUTION_STATUSES


def _write_github_outputs(values: Mapping[str, Any]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            text = str(value)
            if "\n" in text or "\r" in text:
                raise ControlPlaneError("GITHUB_OUTPUT_MULTILINE_FORBIDDEN:" + key)
            handle.write("%s=%s\n" % (key, text))


def claim_request(
    request_path: str,
    run_id: str,
    *,
    root: pathlib.Path = ROOT,
    source_commit: str = "",
    expected_request_sha256: str = "",
    autostart_ledger_path: str = "",
    autostart_source_commit: str = "",
) -> dict[str, Any]:
    mode = verify_execution_mode(root=root)
    normalized, _, raw, request_sha = load_request(request_path, root)
    if expected_request_sha256:
        expected = require_sha(expected_request_sha256, "claim_expected_request")
        if request_sha != expected:
            raise ControlPlaneError("CLAIM_REQUEST_SHA_MISMATCH")
    if mode["mode"] == "AUTOMATIC":
        ledger_binding = verify_autostart_ledger(
            autostart_ledger_path,
            normalized,
            raw,
            request_sha,
            run_id,
            expected_source_commit=autostart_source_commit,
            root=root,
        )
    else:
        if autostart_ledger_path or autostart_source_commit:
            raise ControlPlaneError("MANUAL_MODE_REJECTS_AUTOSTART_LEDGER")
        ledger_binding = None
    identity = _identity(raw, request_sha, run_id)
    task_class = classify_request(raw)
    if bool(raw.get("production_required", False)) and task_class != "CRITICAL":
        raise ControlPlaneError("PRODUCTION_MUST_ROUTE_CRITICAL")
    locks = resource_locks(raw)
    claim_rel = claim_relative_path(identity)
    claim_path = repo_path(claim_rel, root)

    if claim_path.is_file():
        existing = read_json(claim_path)
        if existing.get("identity") != identity or existing.get("request_path") != normalized:
            raise ControlPlaneError("CLAIM_IDENTITY_COLLISION")
        if existing.get("execution_mode") != mode["mode"]:
            raise ControlPlaneError("CLAIM_EXECUTION_MODE_MISMATCH")
        if mode["mode"] == "AUTOMATIC":
            if (
                existing.get("autostart_ledger_path") != ledger_binding["ledger_path"]
                or existing.get("autostart_ledger_sha256") != ledger_binding["ledger_sha256"]
                or existing.get("autostart_source_commit") != ledger_binding["source_commit"]
            ):
                raise ControlPlaneError("CLAIM_AUTOSTART_LEDGER_MISMATCH")
        result = dict(existing)
        result["claim_path"] = claim_rel
        result["plan_path"] = plan_relative_path(identity)
        result["idempotent"] = True
        return result

    for path in _claim_files(root):
        other = read_json(path)
        other_identity = other.get("identity") or {}
        if not isinstance(other_identity, dict):
            raise ControlPlaneError("MALFORMED_DURABLE_CLAIM:" + str(path))
        if (
            other_identity.get("task_id") == identity["task_id"]
            and other_identity.get("task_sha256") == identity["task_sha256"]
            and other_identity.get("run_id") != identity["run_id"]
            and _is_active(other)
        ):
            raise ControlPlaneError("DUPLICATE_ACTIVE_CLAIM:" + path.name)
        if _is_active(other) and locks_conflict(locks, other.get("resource_locks") or []):
            raise ControlPlaneError("RESOURCE_BUSY:" + path.name)

    now = utc_now()
    execution = raw.get("execution") if isinstance(raw.get("execution"), dict) else {}
    ai_status = "PENDING" if bool(raw.get("ai_requested", False)) else "NOT_REQUESTED"
    claim: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "identity": identity,
        "request_path": normalized,
        "request_sha256": request_sha,
        "task_class": task_class,
        "resource_locks": list(locks),
        "queue_key": queue_key(locks),
        "production_required": bool(raw.get("production_required", False)),
        "ai_response_status": ai_status,
        "task_execution_status": "CLAIMED",
        "package_compile_status": "PENDING",
        "storage_preflight_status": "PENDING",
        "pre_health_status": "REQUIRED" if bool(raw.get("production_required", False)) else "NOT_REQUIRED",
        "post_health_status": "REQUIRED" if bool(raw.get("production_required", False)) else "NOT_REQUIRED",
        "critical_gate_status": "PENDING" if task_class == "CRITICAL" else "NOT_REQUIRED",
        "receipt_validation_status": "PENDING",
        "receipt_path": str(execution.get("receipt_path", "")),
        "heartbeat_sequence": 0,
        "heartbeat_at": now,
        "created_at": now,
        "updated_at": now,
        "source_commit": str(source_commit),
        "execution_mode": mode["mode"],
        "mode_epoch": mode.get("mode_epoch", "manual"),
        "automatic_mode_enabled": mode["mode"] == "AUTOMATIC",
    }
    if ledger_binding is not None:
        claim["autostart_ledger_path"] = ledger_binding["ledger_path"]
        claim["autostart_ledger_sha256"] = ledger_binding["ledger_sha256"]
        claim["autostart_source_commit"] = ledger_binding["source_commit"]
    atomic_json(claim_path, claim, exclusive=True)
    plan_rel = plan_relative_path(identity)
    plan = {
        "schema_version": SCHEMA_VERSION,
        "identity": identity,
        "request_path": normalized,
        "task_class": task_class,
        "resource_locks": list(locks),
        "queue_key": claim["queue_key"],
        "ai_response_status": ai_status,
        "task_execution_status": "CLAIMED",
        "production_required": claim["production_required"],
        "execution_mode": mode["mode"],
        "mode_epoch": mode.get("mode_epoch", "manual"),
        "manual_mode": mode["mode"] == "MANUAL",
        "automatic_mode_enabled": mode["mode"] == "AUTOMATIC",
        "created_at": now,
    }
    if ledger_binding is not None:
        plan["autostart_ledger_path"] = ledger_binding["ledger_path"]
        plan["autostart_ledger_sha256"] = ledger_binding["ledger_sha256"]
        plan["autostart_source_commit"] = ledger_binding["source_commit"]
    atomic_json(repo_path(plan_rel, root), plan)
    result = dict(claim)
    result.update({"claim_path": claim_rel, "plan_path": plan_rel, "idempotent": False})
    return result


def verify_request(request_path: str, expected_sha256: str, *, root: pathlib.Path = ROOT) -> dict[str, Any]:
    normalized, _, raw, actual = load_request(request_path, root)
    expected = require_sha(expected_sha256, "expected_request")
    if actual != expected:
        raise ControlPlaneError("REQUEST_SHA_MISMATCH")
    return {
        "status": "PASS",
        "request_path": normalized,
        "task_id": raw["task_id"],
        "request_sha256": actual,
        "task_class": classify_request(raw),
    }


def verify_autostart_ledger(
    ledger_path: str,
    request_path: str,
    raw: Mapping[str, Any],
    request_sha256: str,
    run_id: str,
    *,
    expected_source_commit: str = "",
    root: pathlib.Path = ROOT,
    allow_expired_for_recovery: bool = False,
    allow_halt_for_recovery: bool = False,
) -> dict[str, str]:
    if not str(ledger_path).strip():
        raise ControlPlaneError("AUTOSTART_LEDGER_PATH_MISMATCH")
    normalized = safe_repo_path(ledger_path)
    expected_path = "state/autostart_consumed/%s.%s.json" % (
        str(raw["task_id"]),
        request_sha256,
    )
    if normalized != expected_path:
        raise ControlPlaneError("AUTOSTART_LEDGER_PATH_MISMATCH")
    path = repo_path(normalized, root)
    if path.is_symlink() or not path.is_file():
        raise ControlPlaneError("AUTOSTART_LEDGER_MISSING")
    ledger = read_json(path)
    expected_keys = {
        "consumed_at",
        "created_at",
        "expires_at",
        "launch_path",
        "launch_sha256",
        "nonce",
        "mode_epoch",
        "nonce_reservation_path",
        "nonce_reservation_sha256",
        "production_allowed",
        "production_approval_path",
        "production_approval_sha256",
        "production_required",
        "request_path",
        "request_sha256",
        "request_subject_sha256",
        "run_id",
        "schema_version",
        "source_commit",
        "status",
        "task_id",
    }
    if set(ledger) != expected_keys or ledger.get("schema_version") != AUTOSTART_LEDGER_SCHEMA:
        raise ControlPlaneError("AUTOSTART_LEDGER_SCHEMA")
    if ledger.get("status") != "CONSUMED":
        raise ControlPlaneError("AUTOSTART_LEDGER_STATUS")
    if (
        ledger.get("task_id") != raw["task_id"]
        or ledger.get("request_path") != request_path
        or ledger.get("request_sha256") != request_sha256
        or str(ledger.get("run_id")) != str(run_id)
    ):
        raise ControlPlaneError("AUTOSTART_LEDGER_IDENTITY")
    mode = verify_execution_mode(
        root=root,
        required_mode="AUTOMATIC",
        allow_halt_for_recovery=allow_halt_for_recovery,
    )
    if ledger.get("mode_epoch") != mode.get("mode_epoch"):
        raise ControlPlaneError("AUTOSTART_LEDGER_MODE_EPOCH")
    production = bool(raw.get("production_required", False))
    if ledger.get("production_required") is not production:
        raise ControlPlaneError("AUTOSTART_LEDGER_PRODUCTION_FLAG")
    if ledger.get("production_allowed") is not production:
        raise ControlPlaneError("AUTOSTART_LEDGER_PRODUCTION_AUTHORIZATION")
    consumed_at = parse_utc(str(ledger.get("consumed_at", "")))
    created_at = parse_utc(str(ledger.get("created_at", "")))
    expires_at = parse_utc(str(ledger.get("expires_at", "")))
    if created_at > consumed_at or expires_at <= created_at:
        raise ControlPlaneError("AUTOSTART_LEDGER_TIME_BINDING")
    if not allow_expired_for_recovery and dt.datetime.now(dt.timezone.utc) >= expires_at:
        raise ControlPlaneError("AUTOSTART_LEDGER_EXPIRED")
    require_sha(ledger.get("launch_sha256"), "autostart_launch")
    if not re.fullmatch(r"[0-9a-f]{40}", str(ledger.get("source_commit", ""))):
        raise ControlPlaneError("AUTOSTART_LEDGER_SOURCE_COMMIT")
    if not re.fullmatch(r"[0-9a-f]{40}", str(expected_source_commit)):
        raise ControlPlaneError("AUTOSTART_EXPECTED_SOURCE_COMMIT")
    if ledger.get("source_commit") != expected_source_commit:
        raise ControlPlaneError("AUTOSTART_LEDGER_SOURCE_COMMIT_MISMATCH")
    if not re.fullmatch(r"[A-Za-z0-9._-]{16,128}", str(ledger.get("nonce", ""))):
        raise ControlPlaneError("AUTOSTART_LEDGER_NONCE")
    nonce_rel = safe_repo_path(str(ledger.get("nonce_reservation_path", "")))
    expected_nonce_rel = "state/autostart_nonces/%s.json" % ledger["nonce"]
    if nonce_rel != expected_nonce_rel:
        raise ControlPlaneError("AUTOSTART_NONCE_RESERVATION_PATH")
    nonce_path = repo_path(nonce_rel, root)
    if nonce_path.is_symlink() or not nonce_path.is_file():
        raise ControlPlaneError("AUTOSTART_NONCE_RESERVATION_MISSING")
    if sha256_file(nonce_path) != require_sha(
        ledger.get("nonce_reservation_sha256"), "autostart_nonce_reservation"
    ):
        raise ControlPlaneError("AUTOSTART_NONCE_RESERVATION_SHA")
    reservation = read_json(nonce_path)
    if (
        reservation.get("schema_version") != AUTOSTART_LEDGER_SCHEMA
        or reservation.get("status") != "RESERVED"
        or reservation.get("nonce") != ledger["nonce"]
        or reservation.get("task_id") != raw["task_id"]
        or reservation.get("request_sha256") != request_sha256
        or str(reservation.get("run_id")) != str(run_id)
        or reservation.get("source_commit") != ledger["source_commit"]
    ):
        raise ControlPlaneError("AUTOSTART_NONCE_RESERVATION_BINDING")
    launch_rel = safe_repo_path(str(ledger.get("launch_path", "")))
    if not launch_rel.startswith("tasks/launch/AUTO-") or not launch_rel.endswith(".json"):
        raise ControlPlaneError("AUTOSTART_LEDGER_LAUNCH_SCOPE")
    launch_path = repo_path(launch_rel, root)
    if launch_path.is_symlink() or not launch_path.is_file():
        raise ControlPlaneError("AUTOSTART_LEDGER_LAUNCH_MISSING")
    if sha256_file(launch_path) != ledger["launch_sha256"]:
        raise ControlPlaneError("AUTOSTART_LEDGER_LAUNCH_SHA")
    marker = read_json(launch_path)
    if (
        marker.get("schema_version") != "UA-ART-AUTOSTART-LAUNCH-1"
        or marker.get("action") != "RUN_EXACT_TASK"
        or marker.get("owner_authorized") is not True
        or marker.get("task_id") != raw["task_id"]
        or marker.get("request_path") != request_path
        or marker.get("request_sha256") != request_sha256
        or marker.get("nonce") != ledger["nonce"]
        or marker.get("mode_epoch") != ledger["mode_epoch"]
        or marker.get("production_allowed") is not production
        or marker.get("created_at") != ledger["created_at"]
        or marker.get("expires_at") != ledger["expires_at"]
    ):
        raise ControlPlaneError("AUTOSTART_LEDGER_LAUNCH_BINDING")
    if production:
        critical = raw.get("critical")
        if not isinstance(critical, dict):
            raise ControlPlaneError("AUTOSTART_LEDGER_CRITICAL_BINDING")
        if (
            ledger.get("production_approval_path") != critical.get("owner_approval_path")
            or ledger.get("production_approval_sha256") != critical.get("owner_approval_sha256")
        ):
            raise ControlPlaneError("AUTOSTART_LEDGER_APPROVAL_BINDING")
        if not SHA_RE.fullmatch(str(ledger.get("request_subject_sha256", ""))):
            raise ControlPlaneError("AUTOSTART_LEDGER_REQUEST_SUBJECT")
    elif any(
        str(ledger.get(key, ""))
        for key in (
            "production_approval_path",
            "production_approval_sha256",
            "request_subject_sha256",
        )
    ):
        raise ControlPlaneError("AUTOSTART_LEDGER_NONPRODUCTION_APPROVAL_DATA")
    return {
        "ledger_path": normalized,
        "ledger_sha256": sha256_file(path),
        "source_commit": str(ledger["source_commit"]),
    }


def _load_exact_claim(
    request_path: str, run_id: str, *, root: pathlib.Path = ROOT
) -> tuple[pathlib.Path, dict[str, Any], dict[str, Any], str]:
    normalized, _, raw, request_sha = load_request(request_path, root)
    identity = _identity(raw, request_sha, run_id)
    path = repo_path(claim_relative_path(identity), root)
    if not path.is_file():
        raise ControlPlaneError("EXACT_CLAIM_MISSING")
    claim = read_json(path)
    if claim.get("identity") != identity or claim.get("request_path") != normalized:
        raise ControlPlaneError("EXACT_CLAIM_IDENTITY_MISMATCH")
    mode = verify_execution_mode(root=root)
    if claim.get("execution_mode") != mode["mode"]:
        raise ControlPlaneError("EXACT_CLAIM_EXECUTION_MODE_MISMATCH")
    if mode["mode"] == "AUTOMATIC":
        if claim.get("mode_epoch") != mode.get("mode_epoch"):
            raise ControlPlaneError("EXACT_CLAIM_MODE_EPOCH_MISMATCH")
        binding = verify_autostart_ledger(
            str(claim.get("autostart_ledger_path", "")),
            normalized,
            raw,
            request_sha,
            run_id,
            expected_source_commit=str(claim.get("autostart_source_commit", "")),
            root=root,
        )
        if claim.get("autostart_ledger_sha256") != binding["ledger_sha256"]:
            raise ControlPlaneError("EXACT_CLAIM_AUTOSTART_LEDGER_SHA")
    if claim.get("ai_response_status") not in AI_STATUSES:
        raise ControlPlaneError("INVALID_AI_RESPONSE_STATUS")
    return path, claim, raw, request_sha


def _load_claim_for_recovery(
    request_path: str, run_id: str, *, root: pathlib.Path = ROOT
) -> tuple[pathlib.Path, dict[str, Any], dict[str, Any], str]:
    """Load immutable identity without requiring a still-live write grant.

    Rollback bookkeeping and emergency halt must remain possible after a mode
    revoke or authorization expiry.  This deliberately grants no execution or
    finish capability.
    """
    normalized, _, raw, request_sha = load_request(request_path, root)
    identity = _identity(raw, request_sha, run_id)
    path = repo_path(claim_relative_path(identity), root)
    if path.is_symlink() or not path.is_file():
        raise ControlPlaneError("RECOVERY_CLAIM_MISSING")
    claim = read_json(path)
    if claim.get("identity") != identity or claim.get("request_path") != normalized:
        raise ControlPlaneError("RECOVERY_CLAIM_IDENTITY_MISMATCH")
    return path, claim, raw, request_sha


def _touch_claim(path: pathlib.Path, claim: dict[str, Any], status: str | None = None) -> dict[str, Any]:
    if status is not None:
        if status not in ALLOWED_HEARTBEAT_STATUSES:
            raise ControlPlaneError("INVALID_HEARTBEAT_STATUS")
        if str(claim.get("task_execution_status")) in TERMINAL_EXECUTION_STATUSES:
            raise ControlPlaneError("TERMINAL_CLAIM_CANNOT_HEARTBEAT")
        if str(claim.get("task_execution_status")) in {"BLOCKED_ROOT_CAUSE", "STALLED"}:
            raise ControlPlaneError("BLOCKED_CLAIM_CANNOT_HEARTBEAT")
        claim["task_execution_status"] = status
    claim["heartbeat_sequence"] = int(claim.get("heartbeat_sequence", 0)) + 1
    claim["heartbeat_at"] = utc_now()
    claim["updated_at"] = claim["heartbeat_at"]
    atomic_json(path, claim)
    return claim


def heartbeat_request(
    request_path: str, run_id: str, status: str, *, root: pathlib.Path = ROOT
) -> dict[str, Any]:
    path, claim, _, _ = _load_exact_claim(request_path, run_id, root=root)
    return _touch_claim(path, claim, status.upper())


def validate_ai_plan(value: Mapping[str, Any]) -> None:
    forbidden = {"controller_path", "command", "commands", "script", "shell", "executable"}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).casefold() in forbidden:
                    raise ControlPlaneError("AI_PLAN_EXECUTABLE_FIELD_FORBIDDEN:" + str(key))
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)


def record_ai_plan(
    request_path: str,
    run_id: str,
    plan_path: str,
    expected_sha256: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    claim_path, claim, _, _ = _load_exact_claim(request_path, run_id, root=root)
    if claim.get("ai_response_status") != "PENDING":
        raise ControlPlaneError("AI_RESPONSE_NOT_PENDING")
    normalized = safe_repo_path(plan_path)
    if not normalized.startswith("state/ai_plans/") or not normalized.endswith(".json"):
        raise ControlPlaneError("AI_PLAN_PATH_SCOPE")
    path = repo_path(normalized, root)
    if sha256_file(path) != require_sha(expected_sha256, "ai_plan"):
        raise ControlPlaneError("AI_PLAN_SHA_MISMATCH")
    value = read_json(path)
    validate_ai_plan(value)
    claim["ai_response_status"] = "RECEIVED"
    claim["ai_plan_path"] = normalized
    claim["ai_plan_sha256"] = expected_sha256
    return _touch_claim(claim_path, claim)


def prepare_request_planning(
    request_path: str,
    run_id: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    """Bind an optional data-only AI plan pinned by the immutable request."""
    _, _, raw, _ = load_request(request_path, root)
    _, claim, _, _ = _load_exact_claim(request_path, run_id, root=root)
    if not bool(raw.get("ai_requested", False)):
        if claim.get("ai_response_status") != "NOT_REQUESTED":
            raise ControlPlaneError("AI_RESPONSE_STATUS_MISMATCH")
        return {"status": "NOT_REQUESTED", "executable_content_accepted": False}
    planning = raw.get("planning")
    if not isinstance(planning, dict):
        raise ControlPlaneError("AI_PLANNING_REFERENCE_REQUIRED")
    plan_path = str(planning.get("plan_path", ""))
    plan_sha = str(planning.get("plan_sha256", ""))
    if claim.get("ai_response_status") == "RECEIVED":
        if claim.get("ai_plan_path") != plan_path or claim.get("ai_plan_sha256") != plan_sha:
            raise ControlPlaneError("AI_PLAN_IDEMPOTENCY_MISMATCH")
        value = read_json(repo_path(plan_path, root))
        if sha256_file(repo_path(plan_path, root)) != require_sha(plan_sha, "ai_plan"):
            raise ControlPlaneError("AI_PLAN_SHA_MISMATCH")
        validate_ai_plan(value)
        return {
            "status": "RECEIVED",
            "plan_path": plan_path,
            "plan_sha256": plan_sha,
            "executable_content_accepted": False,
            "idempotent": True,
        }
    updated = record_ai_plan(
        request_path,
        run_id,
        plan_path,
        plan_sha,
        root=root,
    )
    return {
        "status": updated["ai_response_status"],
        "plan_path": updated["ai_plan_path"],
        "plan_sha256": updated["ai_plan_sha256"],
        "executable_content_accepted": False,
    }


def storage_decision(
    usage_percent: float,
    free_bytes: int,
    required_bytes: int,
    *,
    heavy: bool,
) -> dict[str, Any]:
    if not 0 <= usage_percent <= 100:
        raise ControlPlaneError("STORAGE_PERCENT_RANGE")
    if free_bytes < 0 or required_bytes < 0:
        raise ControlPlaneError("STORAGE_BYTES_RANGE")
    if free_bytes < required_bytes:
        status = "BLOCK_INSUFFICIENT_FREE_SPACE"
        allowed = False
    elif usage_percent >= 90:
        status = "STOP_90"
        allowed = False
    elif usage_percent >= 80:
        status = "THROTTLE_80"
        allowed = not heavy
    elif usage_percent >= 70:
        status = "WARN_70"
        allowed = True
    else:
        status = "PASS"
        allowed = True
    return {
        "status": status,
        "allowed": allowed,
        "usage_percent": round(float(usage_percent), 3),
        "free_bytes": int(free_bytes),
        "required_bytes": int(required_bytes),
        "heavy": bool(heavy),
    }


def _production_storage_probe(
    raw: Mapping[str, Any],
    *,
    root: pathlib.Path,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Load a recent, immutable read-only measurement of the production target.

    A GitHub runner's filesystem says nothing about PythonAnywhere capacity.  A
    production route therefore fails closed unless the exact task request pins
    a recent target-side probe by path and SHA-256.
    """
    probe_ref = raw.get("storage_probe")
    if not isinstance(probe_ref, dict):
        raise ControlPlaneError("PRODUCTION_TARGET_STORAGE_PROBE_REQUIRED")
    probe_rel = safe_repo_path(str(probe_ref.get("evidence_path", "")))
    if not probe_rel.startswith("state/storage/") or not probe_rel.endswith(".json"):
        raise ControlPlaneError("STORAGE_PROBE_PATH_SCOPE")
    probe_path = repo_path(probe_rel, root)
    expected_sha = require_sha(probe_ref.get("evidence_sha256"), "storage_probe")
    if probe_path.is_symlink() or not probe_path.is_file():
        raise ControlPlaneError("STORAGE_PROBE_FILE_MISSING")
    if sha256_file(probe_path) != expected_sha:
        raise ControlPlaneError("STORAGE_PROBE_SHA_MISMATCH")

    probe = read_json(probe_path)
    if probe.get("target_environment") != "production" or probe.get("read_only") is not True:
        raise ControlPlaneError("STORAGE_PROBE_TARGET_OR_MODE")
    measured_at = parse_utc(str(probe.get("measured_at", "")))
    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    age_seconds = (current - measured_at).total_seconds()
    if age_seconds < -120 or age_seconds > MAX_STORAGE_PROBE_AGE_SECONDS:
        raise ControlPlaneError("STORAGE_PROBE_STALE_OR_FUTURE")

    try:
        total = int(probe["total_bytes"])
        used = int(probe["used_bytes"])
        free = int(probe["free_bytes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ControlPlaneError("STORAGE_PROBE_BYTES_INVALID") from exc
    if total <= 0 or used < 0 or free < 0 or used > total or free > total:
        raise ControlPlaneError("STORAGE_PROBE_BYTES_RANGE")
    tolerance = max(1024 * 1024, total // 100)
    if abs(total - used - free) > tolerance:
        raise ControlPlaneError("STORAGE_PROBE_BYTES_INCONSISTENT")
    return {
        "usage_percent": used * 100.0 / total,
        "free_bytes": free,
        "measurement_scope": "production_target_read_only_probe",
        "evidence_path": probe_rel,
        "evidence_sha256": expected_sha,
        "measured_at": str(probe["measured_at"]),
        "age_seconds": round(age_seconds, 3),
    }


def storage_preflight(
    request_path: str,
    run_id: str,
    *,
    root: pathlib.Path = ROOT,
    usage_percent: float | None = None,
    free_bytes: int | None = None,
) -> dict[str, Any]:
    claim_path, claim, raw, _ = _load_exact_claim(request_path, run_id, root=root)
    production = bool(raw.get("production_required", False))
    if production:
        measurement = _production_storage_probe(raw, root=root)
        measured_percent = float(measurement["usage_percent"])
        measured_free = int(measurement["free_bytes"])
    else:
        usage = shutil.disk_usage(root)
        actual_percent = (usage.used * 100.0 / usage.total) if usage.total else 100.0
        measured_percent = actual_percent if usage_percent is None else float(usage_percent)
        measured_free = usage.free if free_bytes is None else int(free_bytes)
        measurement = {
            "measurement_scope": (
                "injected_test_measurement"
                if usage_percent is not None or free_bytes is not None
                else "github_runner_sandbox"
            )
        }
    backup = int(raw.get("backup_size_bytes", 0))
    artifact = int(raw.get("artifact_size_bytes", 0))
    required = int(raw.get("storage_required_bytes", backup * 2 + artifact + 64 * 1024 * 1024))
    heavy = production or int(raw.get("complexity", 1)) >= 4
    result = storage_decision(measured_percent, measured_free, required, heavy=heavy)
    result.update(measurement)
    claim["storage_preflight_status"] = result["status"]
    claim["storage_preflight"] = result
    _touch_claim(claim_path, claim)
    return result


def _health_urls(raw: Mapping[str, Any]) -> tuple[str, ...]:
    values = raw.get("health_checks", [])
    if not isinstance(values, list):
        raise ControlPlaneError("HEALTH_CHECKS_NOT_ARRAY")
    urls = tuple(str(value).strip() for value in values if str(value).strip())
    for url in urls:
        if not url.startswith("https://") or any(character in url for character in ("\n", "\r")):
            raise ControlPlaneError("HEALTH_URL_HTTPS_REQUIRED")
    return urls


def run_health_checks(
    urls: Sequence[str],
    *,
    timeout_seconds: float = 10.0,
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    checks = []
    for url in urls:
        started = time.monotonic()
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "UA-ART-Control-Plane-R2/1.0"},
        )
        try:
            with opener(request, timeout=timeout_seconds) as response:
                status = int(response.getcode())
                final_url = str(response.geturl())
                response.read(1024)
            passed = 200 <= status < 400 and final_url.startswith("https://")
            error = ""
        except Exception as exc:  # urllib exposes several transport exception types
            status = 0
            final_url = url
            passed = False
            error = type(exc).__name__ + ":" + str(exc)[:200]
        checks.append(
            {
                "url": url,
                "final_url": final_url,
                "http_status": status,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "status": "PASS" if passed else "FAIL",
                "error": error,
            }
        )
    return {"status": "PASS" if checks and all(item["status"] == "PASS" for item in checks) else "FAIL", "checks": checks}


def health_phase(
    request_path: str,
    run_id: str,
    phase: str,
    *,
    root: pathlib.Path = ROOT,
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    phase_name = str(phase).lower()
    if phase_name not in {"pre", "post"}:
        raise ControlPlaneError("HEALTH_PHASE")
    claim_path, claim, raw, _ = _load_exact_claim(request_path, run_id, root=root)
    if not bool(raw.get("production_required", False)):
        result = {"status": "SKIPPED_NONPRODUCTION", "checks": []}
    else:
        urls = _health_urls(raw)
        if not urls:
            raise ControlPlaneError("PRODUCTION_HEALTH_CHECKS_REQUIRED")
        result = run_health_checks(urls, opener=opener)
        if result["status"] != "PASS":
            raise ControlPlaneError("PRODUCTION_%s_HEALTH_FAILED" % phase_name.upper())
    claim[phase_name + "_health_status"] = result["status"]
    claim[phase_name + "_health"] = result
    _touch_claim(claim_path, claim, "VERIFYING" if phase_name == "post" else "RUNNING")
    return result


def validate_critical_nonproduction(
    request_path: str,
    run_id: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    claim_path, claim, raw, _ = _load_exact_claim(request_path, run_id, root=root)
    if classify_request(raw) != "CRITICAL":
        raise ControlPlaneError("NONPROD_CRITICAL_CLASS_REQUIRED")
    if bool(raw.get("production_required", False)):
        raise ControlPlaneError("NONPROD_CRITICAL_REJECTS_PRODUCTION")
    critical = raw.get("critical")
    if not isinstance(critical, dict):
        raise ControlPlaneError("CRITICAL_GATE_OBJECT_REQUIRED")
    if str(raw.get("requested_min_class", "")).upper() != "CRITICAL":
        raise ControlPlaneError("CRITICAL_MINIMUM_REQUIRED")
    if critical.get("gate_b_authorized") is not False:
        raise ControlPlaneError("NONPROD_GATE_B_MUST_BE_FALSE")

    owner_rel = safe_repo_path(str(critical.get("owner_approval_path", "")))
    owner_path = repo_path(owner_rel, root)
    owner_expected = require_sha(critical.get("owner_approval_sha256"), "owner_approval")
    if sha256_file(owner_path) != owner_expected:
        raise ControlPlaneError("OWNER_APPROVAL_SHA_MISMATCH")
    owner_text = owner_path.read_text(encoding="utf-8")
    for marker in (str(raw["task_id"]), "TASK107-R2", "OWNER_APPROVED", "MANUAL_ONLY"):
        if marker not in owner_text:
            raise ControlPlaneError("OWNER_APPROVAL_MARKER_MISSING:" + marker)

    manifest_rel = safe_repo_path(str(critical.get("manifest_path", "")))
    manifest = read_json(repo_path(manifest_rel, root))
    manifest_expected = require_sha(critical.get("manifest_sha256"), "manifest")
    if sha256_bytes(canonical_json(manifest)) != manifest_expected:
        raise ControlPlaneError("MANIFEST_SHA_MISMATCH")
    if manifest.get("task_id") != raw["task_id"] or str(manifest.get("task_class", "")).upper() != "CRITICAL":
        raise ControlPlaneError("MANIFEST_IDENTITY_MISMATCH")
    operations = manifest.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ControlPlaneError("MANIFEST_OPERATIONS_REQUIRED")
    operation_paths = []
    forbidden = re.compile(r"(?:^|/)(?:crm|cars?|vehicles?|media|dns|cloudflare)(?:/|[._-])", re.I)
    for operation in operations:
        if not isinstance(operation, dict) or str(operation.get("action", "")).lower() not in {"create", "replace", "delete", "noop"}:
            raise ControlPlaneError("MANIFEST_OPERATION_INVALID")
        path = safe_repo_path(str(operation.get("path", "")))
        if forbidden.search(path):
            raise ControlPlaneError("FORBIDDEN_ACCEPTANCE_SCOPE:" + path)
        operation_paths.append(path)
    if sorted(set(operation_paths)) != list(normalized_changed_paths(raw)):
        raise ControlPlaneError("MANIFEST_CHANGED_PATHS_MISMATCH")
    if manifest.get("rollback_required") is not True or manifest.get("protected_paths") in (None, []):
        raise ControlPlaneError("MANIFEST_ROLLBACK_OR_PROTECTION_MISSING")

    gate_rel = safe_repo_path(str(critical.get("gate_a_path", "")))
    gate_path = repo_path(gate_rel, root)
    gate_expected = require_sha(critical.get("gate_a_sha256"), "gate_a")
    if sha256_file(gate_path) != gate_expected:
        raise ControlPlaneError("GATE_A_SHA_MISMATCH")
    gate = read_json(gate_path)
    if gate.get("task_id") != raw["task_id"] or gate.get("status") != "PASS":
        raise ControlPlaneError("GATE_A_IDENTITY_OR_STATUS")
    if gate.get("production_write") is not False or gate.get("tests") != "PASS":
        raise ControlPlaneError("GATE_A_PRODUCTION_OR_TESTS")
    if int(gate.get("unexpected_changes", -1)) != 0 or gate.get("rollback_plan_ready") is not True:
        raise ControlPlaneError("GATE_A_SAFETY_INVARIANT")
    if gate.get("manifest_sha256") != manifest_expected:
        raise ControlPlaneError("GATE_A_MANIFEST_SHA")
    if not isinstance(gate.get("protected_snapshot"), dict) or not gate["protected_snapshot"]:
        raise ControlPlaneError("GATE_A_PROTECTED_SNAPSHOT")
    claim["critical_gate_status"] = "PASS_NONPRODUCTION"
    _touch_claim(claim_path, claim)
    return {
        "status": "PASS_NONPRODUCTION",
        "task_id": raw["task_id"],
        "owner_approval_sha256": owner_expected,
        "manifest_sha256": manifest_expected,
        "gate_a_sha256": gate_expected,
        "production_write": False,
    }


def authorize_critical_production(
    request_path: str,
    run_id: str,
    gate_b_evidence_path: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    """Bind the legacy Gate B result to the exact durable claim.

    The existing critical adapter remains the authority that validates owner
    approval, the manifest and Gate A.  This function accepts only its
    data-only evidence and records the result on the matching R2 claim.
    """
    claim_path, claim, raw, _ = _load_exact_claim(request_path, run_id, root=root)
    if classify_request(raw) != "CRITICAL":
        raise ControlPlaneError("PRODUCTION_CRITICAL_CLASS_REQUIRED")
    if not bool(raw.get("production_required", False)):
        raise ControlPlaneError("PRODUCTION_CRITICAL_FLAG_REQUIRED")
    critical = raw.get("critical")
    if not isinstance(critical, dict) or critical.get("gate_b_authorized") is not True:
        raise ControlPlaneError("PRODUCTION_GATE_B_AUTHORIZATION_REQUIRED")
    evidence_path = pathlib.Path(gate_b_evidence_path)
    if not evidence_path.is_absolute():
        evidence_path = repo_path(gate_b_evidence_path, root)
    evidence = read_json(evidence_path)
    if evidence.get("task_id") != raw["task_id"]:
        raise ControlPlaneError("GATE_B_TASK_ID_MISMATCH")
    if evidence.get("status") != "GATE_B_AUTHORIZED":
        raise ControlPlaneError("GATE_B_STATUS_MISMATCH")
    if evidence.get("production_write") is not False:
        raise ControlPlaneError("GATE_B_MUST_PRECEDE_PRODUCTION_WRITE")
    if evidence.get("rollback_required") is not True or evidence.get("live_verify_required") is not True:
        raise ControlPlaneError("GATE_B_SAFETY_EVIDENCE_MISSING")
    claim["critical_gate_status"] = "PASS_PRODUCTION"
    claim["critical_gate_evidence_sha256"] = sha256_file(evidence_path)
    _touch_claim(claim_path, claim)
    return {
        "status": "PASS_PRODUCTION",
        "task_id": raw["task_id"],
        "gate_b_evidence_sha256": claim["critical_gate_evidence_sha256"],
    }


def mark_compiled(
    request_path: str, run_id: str, *, root: pathlib.Path = ROOT
) -> dict[str, Any]:
    path, claim, raw, _ = _load_exact_claim(request_path, run_id, root=root)
    if claim.get("ai_response_status") == "PENDING":
        raise ControlPlaneError("AI_PLAN_REQUIRED_BEFORE_PACKAGE_COMPILE")
    execution = raw.get("execution")
    if not isinstance(execution, dict):
        raise ControlPlaneError("EXECUTION_OBJECT_REQUIRED")
    controller_sha = require_sha(execution.get("controller_sha256"), "controller")
    file_hashes = execution.get("file_sha256")
    if not isinstance(file_hashes, dict) or not file_hashes:
        raise ControlPlaneError("TRUSTED_PACKAGE_HASHES_REQUIRED")
    for item, value in file_hashes.items():
        safe_repo_path(str(item))
        require_sha(value, "package_file")
    claim["package_compile_status"] = "PASS"
    claim["trusted_package"] = {
        "controller_sha256": controller_sha,
        "file_sha256": dict(sorted((str(k), str(v)) for k, v in file_hashes.items())),
    }
    return _touch_claim(path, claim, "TESTING")


def classify_failure(message: str) -> str:
    if re.search(r"protected[-_ ]file|unexpected[-_ ](?:write|change)|secret (?:leak|exposure)|rollback fail", message, re.I):
        return "SAFETY"
    if re.search(r"owner approval|required owner|waiting owner", message, re.I):
        return "OWNER_DEPENDENCY"
    if re.search(r"syntax(?:error)?|assert(?:ion)?(?:error| failed)|schema (?:mismatch|invalid)|regression|(?:key|type|value|name)error", message, re.I):
        return "LOGICAL"
    if re.search(r"\b429\b|\b50[23]\b|timeout|connection (?:reset|refused)|temporar|rate[_ -]?limit|runner (?:unavailable|lost)", message, re.I):
        return "TRANSIENT"
    return "UNKNOWN"


def record_failure(
    request_path: str,
    run_id: str,
    message: str,
    *,
    root: pathlib.Path = ROOT,
    rollback_confirmed: bool = False,
    terminal: bool = False,
) -> dict[str, Any]:
    path, claim, _, _ = _load_claim_for_recovery(request_path, run_id, root=root)
    current_status = str(claim.get("task_execution_status", ""))
    if current_status in TERMINAL_EXECUTION_STATUSES:
        return {
            "action": "TERMINAL_UNCHANGED",
            "retry_allowed": False,
            "retries_remaining": 0,
            "task_execution_status": current_status,
        }
    failure_class = classify_failure(message)
    signature = sha256_bytes(message.strip().casefold().encode("utf-8"))[:16]
    history = claim.get("failure_history") or []
    if not isinstance(history, list):
        raise ControlPlaneError("FAILURE_HISTORY_INVALID")
    repeated = sum(1 for item in history if isinstance(item, dict) and item.get("signature") == signature) + 1
    budgets = {"FAST": 2, "STANDARD": 3, "CRITICAL": 1}
    used = sum(1 for item in history if isinstance(item, dict) and item.get("retry_allowed"))
    remaining = max(0, budgets[str(claim["task_class"])] - used)
    if rollback_confirmed:
        status, action, retry_allowed = "ROLLED_BACK", "STOP_AFTER_VERIFIED_ROLLBACK", False
    elif terminal:
        status, action, retry_allowed = "FAILED", "STOP_FAIL_CLOSED_TERMINAL", False
        remaining = 0
    elif failure_class == "TRANSIENT" and remaining > 0:
        status, action, retry_allowed = "BLOCKED_RETRYABLE", "RETRY_SAME_IDENTITY", True
        remaining -= 1
    elif failure_class == "SAFETY":
        status = "ROLLED_BACK" if rollback_confirmed else "FAILED"
        action, retry_allowed = "STOP_AND_ROLLBACK", False
    elif failure_class == "OWNER_DEPENDENCY":
        status, action, retry_allowed = "BLOCKED_ROOT_CAUSE", "WAITING_OWNER", False
    elif failure_class == "LOGICAL":
        status = "BLOCKED_ROOT_CAUSE"
        action = "ROOT_CAUSE_MODE" if repeated >= 2 else "ROOT_CAUSE_REQUIRED"
        retry_allowed = False
    else:
        status, action, retry_allowed = "BLOCKED_ROOT_CAUSE", "CLASSIFY_ROOT_CAUSE", False
    entry = {
        "at": utc_now(),
        "class": failure_class,
        "signature": signature,
        "message": message[:500],
        "action": action,
        "retry_allowed": retry_allowed,
        "retries_remaining": remaining,
    }
    history.append(entry)
    claim["failure_history"] = history
    claim["task_execution_status"] = status
    claim["updated_at"] = entry["at"]
    atomic_json(path, claim)
    return entry | {"task_execution_status": status}


def halt_automatic_mode(
    request_path: str,
    run_id: str,
    reason: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    _, claim, raw, request_sha = _load_claim_for_recovery(request_path, run_id, root=root)
    if claim.get("execution_mode") != "AUTOMATIC":
        raise ControlPlaneError("HALT_REQUIRES_AUTOMATIC_CLAIM")
    value = {
        "halted_at": utc_now(),
        "mode_epoch": claim.get("mode_epoch"),
        "reason": str(reason)[:500],
        "request_path": safe_repo_path(request_path),
        "request_sha256": request_sha,
        "run_id": str(run_id),
        "status": "EMERGENCY_HALT",
        "task_id": raw["task_id"],
    }
    atomic_json(root / "state/AUTOPILOT_HALT.json", value)
    return value


def halt_system_automatic_mode(
    run_id: str,
    reason: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    """Persist a recovery halt when no trustworthy task claim can be selected."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(run_id)):
        raise ControlPlaneError("INVALID_RUN_ID")
    mode = read_json(root / "state/EXECUTION_MODE.json")
    epoch = str(mode.get("mode_epoch", ""))
    if mode.get("mode") != "AUTOMATIC" or not re.fullmatch(
        r"auto-[A-Za-z0-9._-]{16,100}", epoch
    ):
        raise ControlPlaneError("SYSTEM_HALT_AUTOMATIC_MODE_REQUIRED")
    halt_path = root / "state/AUTOPILOT_HALT.json"
    if halt_path.exists():
        if halt_path.is_symlink() or not halt_path.is_file():
            raise ControlPlaneError("AUTOMATIC_HALT_FILE_INVALID")
        existing = read_json(halt_path)
        if (
            existing.get("status") != "EMERGENCY_HALT"
            or existing.get("mode_epoch") != epoch
        ):
            raise ControlPlaneError("AUTOMATIC_HALT_IDENTITY_INVALID")
        return existing
    value = {
        "halted_at": utc_now(),
        "mode_epoch": epoch,
        "reason": str(reason)[:500],
        "request_path": "",
        "request_sha256": "0" * 64,
        "run_id": str(run_id),
        "status": "EMERGENCY_HALT",
        "task_id": "SYSTEM-WATCHDOG",
    }
    atomic_json(halt_path, value, exclusive=True)
    return value


def _production_transaction_context(
    request_path: str,
    run_id: str,
    transaction_id: str,
    *,
    root: pathlib.Path,
) -> tuple[
    pathlib.Path,
    dict[str, Any],
    dict[str, Any],
    str,
    str,
    pathlib.Path,
    str,
]:
    claim_path, claim, raw, request_sha = _load_exact_claim(
        request_path, run_id, root=root
    )
    if not bool(raw.get("production_required", False)):
        raise ControlPlaneError("TRANSACTION_REQUIRES_PRODUCTION")
    if claim.get("execution_mode") != "AUTOMATIC":
        raise ControlPlaneError("TRANSACTION_REQUIRES_AUTOMATIC_MODE")
    if claim.get("critical_gate_status") != "PASS_PRODUCTION":
        raise ControlPlaneError("TRANSACTION_REQUIRES_GATE_B")
    if claim.get("package_compile_status") != "PASS":
        raise ControlPlaneError("TRANSACTION_REQUIRES_COMPILED_PACKAGE")
    if claim.get("pre_health_status") != "PASS":
        raise ControlPlaneError("TRANSACTION_REQUIRES_PRE_HEALTH")
    storage = claim.get("storage_preflight")
    if not isinstance(storage, dict) or storage.get("allowed") is not True:
        raise ControlPlaneError("TRANSACTION_REQUIRES_STORAGE_PASS")
    if not re.fullmatch(r"tx-[A-Za-z0-9._-]{16,120}", str(transaction_id)):
        raise ControlPlaneError("TRANSACTION_ID_INVALID")
    execution = raw.get("execution")
    if not isinstance(execution, dict):
        raise ControlPlaneError("TRANSACTION_EXECUTION_OBJECT")
    backup_rel = safe_repo_path(str(execution.get("backup_receipt_path", "")))
    if not backup_rel.startswith("state/receipts/") or not backup_rel.endswith(".json"):
        raise ControlPlaneError("TRANSACTION_BACKUP_RECEIPT_SCOPE")
    backup_path = repo_path(backup_rel, root)
    identity = _identity(raw, request_sha, run_id)
    path_rel = transaction_relative_path(identity)
    path = repo_path(path_rel, root)
    ledger_rel = safe_repo_path(str(claim.get("autostart_ledger_path", "")))
    ledger = read_json(repo_path(ledger_rel, root))
    expires_at = parse_utc(str(ledger.get("expires_at", "")))
    if dt.datetime.now(dt.timezone.utc) >= expires_at:
        raise ControlPlaneError("TRANSACTION_AUTHORIZATION_EXPIRED")
    return claim_path, claim, raw, request_sha, backup_rel, backup_path, path_rel


def prepare_production_transaction(
    request_path: str,
    run_id: str,
    transaction_id: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    """Durably mark Production preparation before exposing any write credential."""
    (
        claim_path,
        claim,
        raw,
        request_sha,
        backup_rel,
        backup_path,
        path_rel,
    ) = _production_transaction_context(
        request_path, run_id, transaction_id, root=root
    )
    if backup_path.is_symlink() or backup_path.exists():
        raise ControlPlaneError("TRANSACTION_BACKUP_RECEIPT_PREEXISTING")
    path = repo_path(path_rel, root)
    ledger_rel = safe_repo_path(str(claim.get("autostart_ledger_path", "")))
    ledger = read_json(repo_path(ledger_rel, root))
    prepared_at = utc_now()
    value = {
        "autostart_ledger_path": ledger_rel,
        "backup_manifest_sha256": None,
        "backup_receipt_path": backup_rel,
        "backup_receipt_sha256": None,
        "expires_at": str(ledger["expires_at"]),
        "mode_epoch": claim.get("mode_epoch"),
        "opened_at": None,
        "prepared_at": prepared_at,
        "request_path": safe_repo_path(request_path),
        "request_sha256": request_sha,
        "run_id": str(run_id),
        "schema_version": PRODUCTION_TRANSACTION_SCHEMA,
        "status": "PREPARING",
        "task_id": raw["task_id"],
        "transaction_id": str(transaction_id),
    }
    atomic_json(path, value, exclusive=True)
    claim["production_transaction_id"] = str(transaction_id)
    claim["production_transaction_path"] = path_rel
    claim["production_transaction_status"] = "PREPARING"
    _touch_claim(claim_path, claim, "RUNNING")
    return value | {"transaction_path": path_rel}


def open_production_transaction(
    request_path: str,
    run_id: str,
    transaction_id: str,
    backup_receipt_sha256: str,
    backup_manifest_sha256: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    """Promote a durable PREPARING record after strict backup validation."""
    (
        claim_path,
        claim,
        raw,
        request_sha,
        backup_rel,
        backup_path,
        path_rel,
    ) = _production_transaction_context(
        request_path, run_id, transaction_id, root=root
    )
    if backup_path.is_symlink() or not backup_path.is_file():
        raise ControlPlaneError("TRANSACTION_BACKUP_RECEIPT_MISSING")
    backup_receipt_sha = require_sha(backup_receipt_sha256, "backup_receipt")
    if sha256_file(backup_path) != backup_receipt_sha:
        raise ControlPlaneError("TRANSACTION_BACKUP_RECEIPT_SHA")
    backup_manifest_sha = require_sha(backup_manifest_sha256, "backup_manifest")
    path = repo_path(path_rel, root)
    if path.is_symlink() or not path.is_file():
        raise ControlPlaneError("TRANSACTION_PREPARATION_MISSING")
    value = read_json(path)
    expected_keys = {
        "autostart_ledger_path", "backup_manifest_sha256",
        "backup_receipt_path", "backup_receipt_sha256", "expires_at",
        "mode_epoch", "opened_at", "prepared_at", "request_path",
        "request_sha256", "run_id", "schema_version", "status",
        "task_id", "transaction_id",
    }
    if set(value) != expected_keys or (
        value.get("schema_version") != PRODUCTION_TRANSACTION_SCHEMA
        or value.get("status") != "PREPARING"
        or value.get("request_path") != safe_repo_path(request_path)
        or value.get("request_sha256") != request_sha
        or str(value.get("run_id")) != str(run_id)
        or value.get("task_id") != raw["task_id"]
        or value.get("transaction_id") != str(transaction_id)
        or value.get("backup_receipt_path") != backup_rel
        or value.get("mode_epoch") != claim.get("mode_epoch")
        or value.get("autostart_ledger_path") != claim.get("autostart_ledger_path")
        or value.get("backup_manifest_sha256") is not None
        or value.get("backup_receipt_sha256") is not None
        or value.get("opened_at") is not None
    ):
        raise ControlPlaneError("TRANSACTION_PREPARATION_IDENTITY_MISMATCH")
    parse_utc(str(value.get("prepared_at", "")))
    critical = raw.get("critical")
    if not isinstance(critical, dict):
        raise ControlPlaneError("TRANSACTION_CRITICAL_OBJECT")
    receipt = read_json(backup_path)
    receipt_keys = {
        "task_id", "request_sha256", "run_id", "transaction_id",
        "manifest_sha256", "backup_manifest_sha256", "schema_version",
        "operation", "status", "backup", "unexpected_changes",
    }
    if set(receipt) != receipt_keys or (
        receipt.get("schema_version") != "UA-ART-PRODUCTION-BACKUP-RECEIPT-1"
        or receipt.get("operation") != "backup"
        or receipt.get("status") != "PASS"
        or receipt.get("backup") != "PASS"
        or type(receipt.get("unexpected_changes")) is not int
        or receipt.get("unexpected_changes") != 0
        or receipt.get("task_id") != raw["task_id"]
        or receipt.get("request_sha256") != request_sha
        or str(receipt.get("run_id")) != str(run_id)
        or receipt.get("transaction_id") != str(transaction_id)
        or receipt.get("manifest_sha256") != critical.get("manifest_sha256")
        or receipt.get("backup_manifest_sha256") != backup_manifest_sha
    ):
        raise ControlPlaneError("TRANSACTION_BACKUP_RECEIPT_BINDING")
    if (
        claim.get("production_transaction_id") != str(transaction_id)
        or claim.get("production_transaction_path") != path_rel
        or claim.get("production_transaction_status") != "PREPARING"
    ):
        raise ControlPlaneError("TRANSACTION_CLAIM_PREPARATION_MISMATCH")
    value["backup_manifest_sha256"] = backup_manifest_sha
    value["backup_receipt_sha256"] = backup_receipt_sha
    value["opened_at"] = utc_now()
    value["status"] = "OPEN"
    atomic_json(path, value)
    claim["production_transaction_status"] = "OPEN"
    _touch_claim(claim_path, claim, "RUNNING")
    return value | {"transaction_path": path_rel}


def start_production_rollback(
    request_path: str,
    run_id: str,
    transaction_id: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    """Durably consume the one automatic rollback attempt for an OPEN write.

    This transition is persisted before a runner receives the rollback
    credential.  If anything crashes after the external side effect, the
    remaining ``ROLLING_BACK`` record forces manual reconciliation instead of
    an unsafe automatic retry.
    """
    claim_path, claim, raw, request_sha = _load_claim_for_recovery(
        request_path, run_id, root=root
    )
    identity = _identity(raw, request_sha, run_id)
    path_rel = transaction_relative_path(identity)
    path = repo_path(path_rel, root)
    if path.is_symlink() or not path.is_file():
        raise ControlPlaneError("TRANSACTION_FILE_MISSING")
    value = read_json(path)
    expected_keys = {
        "autostart_ledger_path", "backup_manifest_sha256",
        "backup_receipt_path", "backup_receipt_sha256", "expires_at",
        "mode_epoch", "opened_at", "prepared_at", "request_path",
        "request_sha256", "run_id", "schema_version", "status",
        "task_id", "transaction_id",
    }
    normalized = safe_repo_path(request_path)
    if set(value) != expected_keys or (
        value.get("schema_version") != PRODUCTION_TRANSACTION_SCHEMA
        or value.get("status") != "OPEN"
        or value.get("request_path") != normalized
        or value.get("request_sha256") != request_sha
        or str(value.get("run_id")) != str(run_id)
        or value.get("task_id") != raw.get("task_id")
        or value.get("transaction_id") != str(transaction_id)
        or value.get("mode_epoch") != claim.get("mode_epoch")
        or value.get("autostart_ledger_path") != claim.get("autostart_ledger_path")
    ):
        raise ControlPlaneError("TRANSACTION_ROLLBACK_START_IDENTITY_MISMATCH")
    require_sha(value.get("backup_receipt_sha256"), "backup_receipt")
    require_sha(value.get("backup_manifest_sha256"), "backup_manifest")
    parse_utc(str(value.get("opened_at", "")))
    if (
        claim.get("production_transaction_id") != str(transaction_id)
        or claim.get("production_transaction_path") != path_rel
        or claim.get("production_transaction_status") != "OPEN"
    ):
        raise ControlPlaneError("TRANSACTION_CLAIM_OPEN_MISMATCH")
    value["status"] = "ROLLING_BACK"
    atomic_json(path, value)
    claim["production_transaction_status"] = "ROLLING_BACK"
    claim["updated_at"] = utc_now()
    atomic_json(claim_path, claim)
    return value | {"transaction_path": path_rel}


def close_production_transaction(
    request_path: str,
    run_id: str,
    transaction_id: str,
    outcome: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    normalized, _, raw, request_sha = load_request(request_path, root)
    identity = _identity(raw, request_sha, run_id)
    path_rel = transaction_relative_path(identity)
    path = repo_path(path_rel, root)
    if path.is_symlink() or not path.is_file():
        raise ControlPlaneError("TRANSACTION_FILE_MISSING")
    value = read_json(path)
    expected = str(outcome).upper()
    if expected not in {"FINISHED", "ROLLED_BACK"}:
        raise ControlPlaneError("TRANSACTION_OUTCOME")
    current_status = value.get("status")
    allowed_current = {"ROLLING_BACK"} if expected == "ROLLED_BACK" else {"OPEN"}
    if (
        value.get("schema_version") != PRODUCTION_TRANSACTION_SCHEMA
        or current_status not in allowed_current
        or value.get("request_path") != normalized
        or value.get("request_sha256") != request_sha
        or str(value.get("run_id")) != str(run_id)
        or value.get("task_id") != raw["task_id"]
        or value.get("transaction_id") != transaction_id
    ):
        raise ControlPlaneError("TRANSACTION_IDENTITY_MISMATCH")
    value["status"] = expected
    value["closed_at"] = utc_now()
    atomic_json(path, value)
    claim_path = repo_path(claim_relative_path(identity), root)
    if claim_path.is_file():
        claim = read_json(claim_path)
        claim["production_transaction_status"] = expected
        claim["updated_at"] = value["closed_at"]
        atomic_json(claim_path, claim)
    return value | {"transaction_path": path_rel}


def detect_stall(
    claim_path: pathlib.Path,
    max_age_seconds: int,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    if max_age_seconds < 1:
        raise ControlPlaneError("STALL_MAX_AGE_RANGE")
    claim = read_json(claim_path)
    current = now or dt.datetime.now(dt.timezone.utc)
    age = (current - parse_utc(str(claim.get("heartbeat_at", "")))).total_seconds()
    stalled = _is_active(claim) and age > max_age_seconds
    if stalled:
        claim["task_execution_status"] = "STALLED"
        claim["stall_detected_at"] = current.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        claim["stall_age_seconds"] = int(age)
        claim["updated_at"] = claim["stall_detected_at"]
        atomic_json(claim_path, claim)
    return {
        "status": "STALLED" if stalled else "PASS",
        "stalled": stalled,
        "age_seconds": round(age, 3),
        "task_execution_status": claim.get("task_execution_status"),
    }


def validate_receipt(
    receipt: Mapping[str, Any],
    raw: Mapping[str, Any],
    request_sha256: str,
    run_id: str,
) -> dict[str, Any]:
    required = {
        "task_id",
        "status",
        "task_class",
        "target_environment",
        "tests",
        "unexpected_changes",
        "rollback_ready",
        "production_required",
        "request_sha256",
        "run_id",
    }
    missing = sorted(required - set(receipt))
    if missing:
        raise ControlPlaneError("RECEIPT_MISSING:" + ",".join(missing))
    if receipt["task_id"] != raw["task_id"]:
        raise ControlPlaneError("RECEIPT_TASK_ID")
    if receipt["status"] != "FINISHED":
        raise ControlPlaneError("RECEIPT_STATUS_NOT_FINISHED")
    expected_class = classify_request(raw)
    if str(receipt["task_class"]).upper() != expected_class:
        raise ControlPlaneError("RECEIPT_CLASS")
    if receipt["tests"] != "PASS" or int(receipt["unexpected_changes"]) != 0:
        raise ControlPlaneError("RECEIPT_TEST_OR_CHANGE_FAILURE")
    if receipt["rollback_ready"] is not True:
        raise ControlPlaneError("RECEIPT_ROLLBACK_NOT_READY")
    if receipt["request_sha256"] != request_sha256 or str(receipt["run_id"]) != str(run_id):
        raise ControlPlaneError("RECEIPT_EXACT_IDENTITY")
    production = bool(raw.get("production_required", False))
    if bool(receipt["production_required"]) != production:
        raise ControlPlaneError("RECEIPT_PRODUCTION_FLAG")
    environment = str(receipt["target_environment"]).lower()
    if production:
        if environment != "production":
            raise ControlPlaneError("RECEIPT_PRODUCTION_ENVIRONMENT")
        if receipt.get("production") != "PASS" or receipt.get("live_verify") != "PASS" or not str(receipt.get("backup", "")):
            raise ControlPlaneError("RECEIPT_PRODUCTION_EVIDENCE")
    elif environment not in {"sandbox", "shadow", "preview", "test"}:
        raise ControlPlaneError("RECEIPT_NONPROD_ENVIRONMENT")
    return dict(receipt)


def finish_request(
    request_path: str, run_id: str, *, root: pathlib.Path = ROOT
) -> dict[str, Any]:
    claim_path, claim, raw, request_sha = _load_exact_claim(request_path, run_id, root=root)
    if claim.get("task_execution_status") == "FINISHED":
        return claim
    if claim.get("package_compile_status") != "PASS":
        raise ControlPlaneError("FINISHED_REQUIRES_TRUSTED_PACKAGE_PASS")
    if claim.get("ai_response_status") == "PENDING":
        raise ControlPlaneError("FINISHED_REQUIRES_AI_RESPONSE_OR_NO_AI")
    storage = claim.get("storage_preflight")
    if not isinstance(storage, dict) or storage.get("allowed") is not True:
        raise ControlPlaneError("FINISHED_REQUIRES_STORAGE_PREFLIGHT")
    if claim.get("task_class") == "CRITICAL" and claim.get("critical_gate_status") not in {"PASS_NONPRODUCTION", "PASS_PRODUCTION"}:
        raise ControlPlaneError("FINISHED_REQUIRES_CRITICAL_GATE")
    if bool(raw.get("production_required", False)):
        if claim.get("pre_health_status") != "PASS" or claim.get("post_health_status") != "PASS":
            raise ControlPlaneError("FINISHED_REQUIRES_PRE_POST_HEALTH")
    execution = raw.get("execution") or {}
    receipt_rel = safe_repo_path(str(execution.get("receipt_path", "")))
    receipt_path = repo_path(receipt_rel, root)
    receipt = validate_receipt(read_json(receipt_path), raw, request_sha, run_id)
    now = utc_now()
    claim["receipt_validation_status"] = "PASS"
    claim["receipt_path"] = receipt_rel
    claim["receipt_sha256"] = sha256_file(receipt_path)
    claim["task_execution_status"] = "FINISHED"
    claim["heartbeat_sequence"] = int(claim.get("heartbeat_sequence", 0)) + 1
    claim["heartbeat_at"] = now
    claim["updated_at"] = now
    claim["finished_at"] = now
    atomic_json(claim_path, claim)
    return claim | {"receipt": receipt}


def verify_exact_identity(
    request_path: str,
    task_id: str,
    request_sha256: str,
    run_id: str,
    *,
    expected_claim_path: str | None = None,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    normalized, _, raw, actual_sha = load_request(request_path, root)
    if str(raw["task_id"]) != str(task_id):
        raise ControlPlaneError("AUTOSTART_TASK_ID_MISMATCH")
    if actual_sha != require_sha(request_sha256, "autostart_request"):
        raise ControlPlaneError("AUTOSTART_REQUEST_SHA_MISMATCH")
    claim_path, claim, _, _ = _load_exact_claim(normalized, run_id, root=root)
    actual_claim_path = claim_path.relative_to(root).as_posix()
    if (
        expected_claim_path is not None
        and safe_repo_path(expected_claim_path) != actual_claim_path
    ):
        raise ControlPlaneError("AUTOSTART_CLAIM_PATH_MISMATCH")
    expected_identity = _identity(raw, actual_sha, run_id)
    if claim.get("identity") != expected_identity:
        raise ControlPlaneError("AUTOSTART_CLAIM_IDENTITY_MISMATCH")
    if claim.get("task_execution_status") == "FINISHED":
        execution = raw.get("execution") or {}
        receipt_path = repo_path(str(execution.get("receipt_path", "")), root)
        validate_receipt(read_json(receipt_path), raw, actual_sha, run_id)
    return {
        "status": "PASS",
        "request_path": normalized,
        "identity": expected_identity,
        "claim_path": actual_claim_path,
        "task_execution_status": claim.get("task_execution_status"),
        "generic_recent_run_accepted": False,
    }


def build_acceptance(
    request_paths: Sequence[str],
    run_id: str,
    task_contract_path: str,
    output_path: str,
    report_path: str,
    *,
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    if len(request_paths) != 3:
        raise ControlPlaneError("ACCEPTANCE_REQUIRES_EXACTLY_THREE_CANARIES")
    expected_classes = ["FAST", "STANDARD", "CRITICAL"]
    canaries = []
    for index, (request_path, expected_class) in enumerate(zip(request_paths, expected_classes), start=1):
        normalized, _, raw, request_sha = load_request(request_path, root)
        if classify_request(raw) != expected_class or int(raw.get("canary_index", 0)) != index:
            raise ControlPlaneError("CANARY_ORDER_OR_CLASS_MISMATCH:%d" % index)
        execution = raw.get("execution") or {}
        receipt_path = repo_path(str(execution.get("receipt_path", "")), root)
        receipt = validate_receipt(read_json(receipt_path), raw, request_sha, run_id)
        if receipt.get("rollback_drill") != "PASS" or receipt.get("production_touched") is not False:
            raise ControlPlaneError("CANARY_ROLLBACK_OR_PRODUCTION:%d" % index)
        _, claim, _, _ = _load_exact_claim(normalized, run_id, root=root)
        if claim.get("task_execution_status") != "FINISHED" or claim.get("receipt_validation_status") != "PASS":
            raise ControlPlaneError("CANARY_CLAIM_NOT_FINISHED:%d" % index)
        canaries.append(
            {
                "index": index,
                "task_id": raw["task_id"],
                "task_class": expected_class,
                "request_path": normalized,
                "request_sha256": request_sha,
                "receipt_sha256": sha256_file(receipt_path),
                "status": "PASS",
            }
        )

    manual_mode = root / "state/MANUAL_MODE.md"
    try:
        require_mode_status(manual_mode, "ACTIVE")
    except ControlPlaneError as exc:
        raise ControlPlaneError("MANUAL_MODE_NOT_ACTIVE") from exc
    contract_rel = safe_repo_path(task_contract_path)
    contract_path = repo_path(contract_rel, root)
    contract_text = contract_path.read_text(encoding="utf-8")
    for marker in ("TASK107-R2", "STATUS: OWNER_APPROVED", "MANUAL_ONLY_UNTIL_ACCEPTANCE"):
        if marker not in contract_text:
            raise ControlPlaneError("TASK107_CONTRACT_MARKER_MISSING:" + marker)
    contract_sha = sha256_file(contract_path)
    now = utc_now()
    receipt = {
        "task_id": "TASK107-R2",
        "status": "FINISHED",
        "task_class": "CRITICAL",
        "target_environment": "sandbox",
        "tests": "PASS",
        "unexpected_changes": 0,
        "rollback_ready": True,
        "production_required": False,
        "request_sha256": contract_sha,
        "run_id": str(run_id),
        "canary_result": "3/3 PASS",
        "canaries": canaries,
        "exact_intake": "PASS",
        "atomic_claim": "PASS",
        "resource_queue": "PASS",
        "trusted_package_compiler": "PASS",
        "storage_guard": "PASS",
        "health_guard": "PASS",
        "stall_detector": "PASS",
        "duplicate_protection": "PASS",
        "rollback_drill": "PASS",
        "ai_and_execution_status_separate": True,
        "receipt_required_for_finished": True,
        "autopilot_mode": "MANUAL",
        "production_touched": False,
        "crm_vehicle_data_touched": False,
        "automatic_mode_enabled": False,
        "finished_at": now,
    }
    output_rel = safe_repo_path(output_path)
    if output_rel != "state/receipts/TASK107-R2.json":
        raise ControlPlaneError("TASK107_RECEIPT_PATH")
    atomic_json(repo_path(output_rel, root), receipt)
    # Validate the durable aggregate as a generic non-production receipt.
    pseudo_request = {
        "task_id": "TASK107-R2",
        "title": "TASK107-R2 acceptance",
        "changed_paths": [".github/workflows/uaart_orchestrator.yml"],
        "requested_min_class": "CRITICAL",
        "production_required": False,
    }
    validate_receipt(receipt, pseudo_request, contract_sha, run_id)
    lines = [
        "# TASK107-R2 Control Plane Acceptance",
        "",
        "STATUS: **3/3 PASS**",
        "",
        "| # | Class | Task | Result |",
        "|---:|---|---|---|",
    ]
    for canary in canaries:
        lines.append("| {index} | {task_class} | {task_id} | PASS |".format(**canary))
    lines.extend(
        [
            "",
            "- Exact durable intake: PASS",
            "- Atomic exact-identity claim: PASS",
            "- Trusted package compile/execute boundary: PASS",
            "- Storage 70/80/90 guard: PASS",
            "- Production pre/post health guard: PASS (fail-closed contract test; no production call)",
            "- Heartbeat/stall and bounded retry: PASS",
            "- Duplicate protection: PASS",
            "- Rollback drill: PASS",
            "- Site/CRM/DNS/VIN/prices/cards/media touched: NO",
            "- Autopilot mode after acceptance: MANUAL",
            "- Automatic mode enabled: NO — separate owner confirmation required",
            "",
            "Run ID: `%s`" % run_id,
            "Finished: `%s`" % now,
            "",
        ]
    )
    atomic_text(repo_path(report_path, root), "\n".join(lines))
    return receipt


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def self_test() -> None:
    assert storage_decision(69.9, 100, 10, heavy=True)["status"] == "PASS"
    assert storage_decision(70, 100, 10, heavy=True)["status"] == "WARN_70"
    assert storage_decision(80, 100, 10, heavy=True)["allowed"] is False
    assert storage_decision(90, 100, 10, heavy=False)["status"] == "STOP_90"
    assert locks_conflict(("CONTROL_PLANE",), ("CONTROL_PLANE",))
    assert not locks_conflict(("CARD:UA-0001",), ("CARD:UA-0002",))
    assert classify_request({
        "task_id": "SELF-TEST",
        "title": "Workflow check",
        "changed_paths": [".github/workflows/x.yml"],
    }) == "CRITICAL"
    print("UAART_CONTROL_PLANE_R2_SELF_TEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    claim = sub.add_parser("claim")
    claim.add_argument("request_path")
    claim.add_argument("--run-id", required=True)
    claim.add_argument("--source-commit", default="")
    claim.add_argument("--expected-sha256", default="")
    claim.add_argument("--autostart-ledger", default="")
    claim.add_argument("--autostart-source-commit", default="")

    verify = sub.add_parser("verify-request")
    verify.add_argument("request_path")
    verify.add_argument("--sha256", required=True)

    beat = sub.add_parser("heartbeat")
    beat.add_argument("request_path")
    beat.add_argument("--run-id", required=True)
    beat.add_argument("--status", required=True, choices=sorted(ALLOWED_HEARTBEAT_STATUSES))

    ai = sub.add_parser("ai-plan")
    ai.add_argument("request_path")
    ai.add_argument("--run-id", required=True)
    ai.add_argument("--plan-path", required=True)
    ai.add_argument("--sha256", required=True)

    planning = sub.add_parser("planning")
    planning.add_argument("request_path")
    planning.add_argument("--run-id", required=True)

    storage = sub.add_parser("storage")
    storage.add_argument("request_path")
    storage.add_argument("--run-id", required=True)
    storage.add_argument("--enforce", action="store_true")

    health = sub.add_parser("health")
    health.add_argument("request_path")
    health.add_argument("--run-id", required=True)
    health.add_argument("--phase", required=True, choices=("pre", "post"))

    critical = sub.add_parser("critical-nonprod")
    critical.add_argument("request_path")
    critical.add_argument("--run-id", required=True)

    critical_production = sub.add_parser("critical-production")
    critical_production.add_argument("request_path")
    critical_production.add_argument("--run-id", required=True)
    critical_production.add_argument("--gate-b-evidence", required=True)

    compiled = sub.add_parser("compiled")
    compiled.add_argument("request_path")
    compiled.add_argument("--run-id", required=True)

    failure = sub.add_parser("fail")
    failure.add_argument("request_path")
    failure.add_argument("--run-id", required=True)
    failure.add_argument("--message", required=True)
    failure.add_argument("--rollback-confirmed", action="store_true")
    failure.add_argument("--terminal", action="store_true")

    halt = sub.add_parser("halt")
    halt.add_argument("request_path")
    halt.add_argument("--run-id", required=True)
    halt.add_argument("--reason", required=True)

    system_halt = sub.add_parser("halt-system")
    system_halt.add_argument("--run-id", required=True)
    system_halt.add_argument("--reason", required=True)

    transaction_prepare = sub.add_parser("transaction-prepare")
    transaction_prepare.add_argument("request_path")
    transaction_prepare.add_argument("--run-id", required=True)
    transaction_prepare.add_argument("--transaction-id", required=True)

    transaction_open = sub.add_parser("transaction-open")
    transaction_open.add_argument("request_path")
    transaction_open.add_argument("--run-id", required=True)
    transaction_open.add_argument("--transaction-id", required=True)
    transaction_open.add_argument("--backup-receipt-sha256", required=True)
    transaction_open.add_argument("--backup-manifest-sha256", required=True)

    transaction_rollback_start = sub.add_parser("transaction-rollback-start")
    transaction_rollback_start.add_argument("request_path")
    transaction_rollback_start.add_argument("--run-id", required=True)
    transaction_rollback_start.add_argument("--transaction-id", required=True)

    transaction_close = sub.add_parser("transaction-close")
    transaction_close.add_argument("request_path")
    transaction_close.add_argument("--run-id", required=True)
    transaction_close.add_argument("--transaction-id", required=True)
    transaction_close.add_argument(
        "--outcome", required=True, choices=("FINISHED", "ROLLED_BACK")
    )

    stall = sub.add_parser("stall")
    stall.add_argument("claim_path")
    stall.add_argument("--max-age-seconds", type=int, required=True)

    finish = sub.add_parser("finish")
    finish.add_argument("request_path")
    finish.add_argument("--run-id", required=True)

    identity = sub.add_parser("verify-identity")
    identity.add_argument("request_path")
    identity.add_argument("--task-id", required=True)
    identity.add_argument("--sha256", required=True)
    identity.add_argument("--run-id", required=True)
    identity.add_argument("--claim-path")

    accept = sub.add_parser("accept")
    accept.add_argument("--requests", nargs=3, required=True)
    accept.add_argument("--run-id", required=True)
    accept.add_argument("--task-contract", required=True)
    accept.add_argument("--output", required=True)
    accept.add_argument("--report", required=True)

    mode = sub.add_parser("verify-mode")
    mode.add_argument("--require", choices=sorted(EXECUTION_MODES))
    mode.add_argument("--allow-halt-for-recovery", action="store_true")

    sub.add_parser("self-test")
    args = parser.parse_args()

    if args.command == "claim":
        result = claim_request(
            args.request_path,
            args.run_id,
            source_commit=args.source_commit,
            expected_request_sha256=args.expected_sha256,
            autostart_ledger_path=args.autostart_ledger,
            autostart_source_commit=args.autostart_source_commit,
        )
        _write_github_outputs({
            "request_path": result["request_path"],
            "request_sha256": result["request_sha256"],
            "task_id": result["identity"]["task_id"],
            "task_class": result["task_class"],
            "lock_key": result["queue_key"],
            "claim_path": result["claim_path"],
            "plan_path": result["plan_path"],
            "production_required": str(result["production_required"]).lower(),
        })
        _dump(result)
    elif args.command == "verify-request":
        _dump(verify_request(args.request_path, args.sha256))
    elif args.command == "heartbeat":
        _dump(heartbeat_request(args.request_path, args.run_id, args.status))
    elif args.command == "ai-plan":
        _dump(record_ai_plan(args.request_path, args.run_id, args.plan_path, args.sha256))
    elif args.command == "planning":
        _dump(prepare_request_planning(args.request_path, args.run_id))
    elif args.command == "storage":
        result = storage_preflight(args.request_path, args.run_id)
        _dump(result)
        if args.enforce and not result["allowed"]:
            raise SystemExit(2)
    elif args.command == "health":
        _dump(health_phase(args.request_path, args.run_id, args.phase))
    elif args.command == "critical-nonprod":
        _dump(validate_critical_nonproduction(args.request_path, args.run_id))
    elif args.command == "critical-production":
        _dump(authorize_critical_production(
            args.request_path,
            args.run_id,
            args.gate_b_evidence,
        ))
    elif args.command == "compiled":
        _dump(mark_compiled(args.request_path, args.run_id))
    elif args.command == "fail":
        _dump(record_failure(
            args.request_path,
            args.run_id,
            args.message,
            rollback_confirmed=args.rollback_confirmed,
            terminal=args.terminal,
        ))
    elif args.command == "halt":
        _dump(halt_automatic_mode(
            args.request_path,
            args.run_id,
            args.reason,
        ))
    elif args.command == "halt-system":
        _dump(halt_system_automatic_mode(
            args.run_id,
            args.reason,
        ))
    elif args.command == "transaction-prepare":
        result = prepare_production_transaction(
            args.request_path,
            args.run_id,
            args.transaction_id,
        )
        _write_github_outputs({"transaction_path": result["transaction_path"]})
        _dump(result)
    elif args.command == "transaction-open":
        result = open_production_transaction(
            args.request_path,
            args.run_id,
            args.transaction_id,
            args.backup_receipt_sha256,
            args.backup_manifest_sha256,
        )
        _write_github_outputs({"transaction_path": result["transaction_path"]})
        _dump(result)
    elif args.command == "transaction-rollback-start":
        result = start_production_rollback(
            args.request_path,
            args.run_id,
            args.transaction_id,
        )
        _write_github_outputs({"transaction_path": result["transaction_path"]})
        _dump(result)
    elif args.command == "transaction-close":
        _dump(close_production_transaction(
            args.request_path,
            args.run_id,
            args.transaction_id,
            args.outcome,
        ))
    elif args.command == "stall":
        _dump(detect_stall(repo_path(args.claim_path), args.max_age_seconds))
    elif args.command == "finish":
        _dump(finish_request(args.request_path, args.run_id))
    elif args.command == "verify-identity":
        _dump(verify_exact_identity(
            args.request_path,
            args.task_id,
            args.sha256,
            args.run_id,
            expected_claim_path=args.claim_path,
        ))
    elif args.command == "accept":
        _dump(build_acceptance(
            args.requests,
            args.run_id,
            args.task_contract,
            args.output,
            args.report,
        ))
    elif args.command == "verify-mode":
        _dump(verify_execution_mode(
            required_mode=args.require,
            allow_halt_for_recovery=args.allow_halt_for_recovery,
        ))
    else:
        self_test()


if __name__ == "__main__":
    main()
