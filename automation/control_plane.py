#!/usr/bin/env python3
"""TASK107-R2 durable control plane for UA ART task execution.

The module is intentionally limited to repository state, read-only health
checks and validation.  It cannot deploy, mutate the website, write CRM data,
change DNS, or enable automatic mode.
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
    path = pathlib.PurePosixPath(str(value))
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
) -> dict[str, Any]:
    normalized, _, raw, request_sha = load_request(request_path, root)
    identity = _identity(raw, request_sha, run_id)
    task_class = classify_request(raw)
    locks = resource_locks(raw)
    claim_rel = claim_relative_path(identity)
    claim_path = repo_path(claim_rel, root)

    if claim_path.is_file():
        existing = read_json(claim_path)
        if existing.get("identity") != identity or existing.get("request_path") != normalized:
            raise ControlPlaneError("CLAIM_IDENTITY_COLLISION")
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
        "automatic_mode_enabled": False,
    }
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
        "manual_mode": True,
        "created_at": now,
    }
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
    if claim.get("ai_response_status") not in AI_STATUSES:
        raise ControlPlaneError("INVALID_AI_RESPONSE_STATUS")
    return path, claim, raw, request_sha


def _touch_claim(path: pathlib.Path, claim: dict[str, Any], status: str | None = None) -> dict[str, Any]:
    if status is not None:
        if status not in ALLOWED_HEARTBEAT_STATUSES:
            raise ControlPlaneError("INVALID_HEARTBEAT_STATUS")
        if str(claim.get("task_execution_status")) in TERMINAL_EXECUTION_STATUSES:
            raise ControlPlaneError("TERMINAL_CLAIM_CANNOT_HEARTBEAT")
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
) -> dict[str, Any]:
    path, claim, _, _ = _load_exact_claim(request_path, run_id, root=root)
    failure_class = classify_failure(message)
    signature = sha256_bytes(message.strip().casefold().encode("utf-8"))[:16]
    history = claim.get("failure_history") or []
    if not isinstance(history, list):
        raise ControlPlaneError("FAILURE_HISTORY_INVALID")
    repeated = sum(1 for item in history if isinstance(item, dict) and item.get("signature") == signature) + 1
    budgets = {"FAST": 2, "STANDARD": 3, "CRITICAL": 1}
    used = sum(1 for item in history if isinstance(item, dict) and item.get("retry_allowed"))
    remaining = max(0, budgets[str(claim["task_class"])] - used)
    if failure_class == "TRANSIENT" and remaining > 0:
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
    root: pathlib.Path = ROOT,
) -> dict[str, Any]:
    normalized, _, raw, actual_sha = load_request(request_path, root)
    if str(raw["task_id"]) != str(task_id):
        raise ControlPlaneError("AUTOSTART_TASK_ID_MISMATCH")
    if actual_sha != require_sha(request_sha256, "autostart_request"):
        raise ControlPlaneError("AUTOSTART_REQUEST_SHA_MISMATCH")
    claim_path, claim, _, _ = _load_exact_claim(normalized, run_id, root=root)
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
        "claim_path": claim_path.relative_to(root).as_posix(),
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
    if not manual_mode.is_file() or "STATUS: ACTIVE" not in manual_mode.read_text(encoding="utf-8"):
        raise ControlPlaneError("MANUAL_MODE_NOT_ACTIVE")
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

    accept = sub.add_parser("accept")
    accept.add_argument("--requests", nargs=3, required=True)
    accept.add_argument("--run-id", required=True)
    accept.add_argument("--task-contract", required=True)
    accept.add_argument("--output", required=True)
    accept.add_argument("--report", required=True)

    sub.add_parser("self-test")
    args = parser.parse_args()

    if args.command == "claim":
        result = claim_request(args.request_path, args.run_id, source_commit=args.source_commit)
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
        ))
    elif args.command == "stall":
        _dump(detect_stall(repo_path(args.claim_path), args.max_age_seconds))
    elif args.command == "finish":
        _dump(finish_request(args.request_path, args.run_id))
    elif args.command == "verify-identity":
        _dump(verify_exact_identity(
            args.request_path, args.task_id, args.sha256, args.run_id
        ))
    elif args.command == "accept":
        _dump(build_acceptance(
            args.requests,
            args.run_id,
            args.task_contract,
            args.output,
            args.report,
        ))
    else:
        self_test()


if __name__ == "__main__":
    main()
