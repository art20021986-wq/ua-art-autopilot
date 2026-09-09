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
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import stat
import subprocess
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
    # Execute source bytes directly: a timestamp-matching ignored bytecode
    # cache must not supersede the source pinned by the workflow bootstrap.
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
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



# Recovery registration is deliberately hosted in this already pinned runtime.
# These commands produce DATA ONLY proposals outside the checkout. The existing
# scheduled watchdog above keeps its original discovery/rollback behavior.
RECOVERY_TASK = "UA-ART-RECOVERY-TASK120-002"
RECOVERY_REPOSITORY = "art20021986-wq/ua-art-autopilot"
RECOVERY_REPOSITORY_ID = "1346296029"
RECOVERY_OWNER = "art20021986-wq"
RECOVERY_OWNER_ID = "321059821"
RECOVERY_WORKFLOW = ".github/workflows/uaart_transaction_watchdog.yml"
RECOVERY_HALT = "state/AUTOPILOT_HALT.json"
RECOVERY_HALT_SHA = "35c8f42ec20d33f259cbf87aaaa193c86c4d5ae469fa4a8e67e6d049ce0091e9"
RECOVERY_FAILED_TASK = "TASK120-PUBLISH-UA-0017-UA-0018"
RECOVERY_FAILED_RUN = "34134692609"
RECOVERY_REQUEST_SHA = "a4662a876b037595742a31e34394b27d3e40bcbb75e2915df1ecdc0cb01b4442"
RECOVERY_EPOCH = "auto-20260904T174904Z-global-guard-04"
RECOVERY_RECON = "state/reconciliations/" + RECOVERY_FAILED_TASK + "." + RECOVERY_FAILED_RUN + ".no-production-write.evidence-v2.json"
RECOVERY_RECON_SHA = "ce4f04f5fad0c1dc61544a029e4301868433b1a50c9ffaae93dce206bc6c4b3b"
RECOVERY_REQUEST = "tasks/requests/" + RECOVERY_FAILED_TASK + ".json"
RECOVERY_ID = RECOVERY_FAILED_TASK + "." + RECOVERY_REQUEST_SHA + "." + RECOVERY_FAILED_RUN + ".json"
RECOVERY_TRANSACTION = "state/transactions/" + RECOVERY_ID
RECOVERY_CLAIM = "state/claims/" + RECOVERY_ID
RECOVERY_LEDGER = "state/autostart_consumed/" + RECOVERY_FAILED_TASK + "." + RECOVERY_REQUEST_SHA + ".json"
RECOVERY_CANARY = "state/recovery_route_receipts/" + RECOVERY_TASK + ".json"
RECOVERY_ARCHIVE = "state/halt_history/" + RECOVERY_TASK + "/halt.json"
RECOVERY_RECEIPT = "state/halt_history/" + RECOVERY_TASK + "/receipt.json"
RECOVERY_SCOPES = ("state/claims/", "state/transactions/", "state/autostart_consumed/",
                   "state/autostart_nonces/", "tasks/launch/", "tasks/requests/",
                   ".github/workflows/", "state/recovery_route_receipts/",
                   "state/halt_history/", "state/runtime_activations/")
RECOVERY_QUEUE_STATUSES = ("pending", "queued", "in_progress", "requested", "waiting")


def _rr(condition: Any, code: str) -> None:
    if not condition:
        raise WatchdogError("RECOVERY_" + code)


def _rsha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _rcanonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _rjson(payload: bytes) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _rr(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        return json.loads(payload, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise WatchdogError("RECOVERY_INVALID_JSON") from exc


def _robject(payload: bytes) -> dict[str, Any]:
    value = _rjson(payload)
    _rr(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def _rpath(path: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(os.path.abspath(path))
    for item in (*reversed(path.parents), path):
        _rr(not item.is_symlink(), "SYMLINK_REFUSED")
    return path


def _rread(path: pathlib.Path, limit: int = 16 * 1024 * 1024) -> bytes:
    path = _rpath(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        _rr(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "FILE_TYPE_OR_SIZE")
        payload = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    current = path.stat(follow_symlinks=False)
    _rr(len(payload) <= limit and all(getattr(before, key) == getattr(after, key) == getattr(current, key)
        for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")), "INPUT_CHANGED")
    return payload


def _rtime(value: Any) -> dt.datetime:
    _rr(isinstance(value, str), "INVALID_TIME")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WatchdogError("RECOVERY_INVALID_TIME") from exc
    _rr(parsed.tzinfo is not None, "TIMEZONE_REQUIRED")
    return parsed.astimezone(dt.timezone.utc)


def _rgit(root: pathlib.Path, *args: str) -> bytes:
    # Read-only calls only; no inherited Git configuration, credential helper,
    # hooks, replacements, shell, remote URL, token, or network operation.
    allowed = {"rev-parse", "status", "ls-tree", "show", "diff-tree", "log"}
    _rr(args and args[0] in allowed, "GIT_READ_ONLY")
    result = subprocess.run(["/usr/bin/git", "--no-replace-objects", "-c", "core.fsmonitor=false",
        "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=", *args], cwd=root,
        env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=30, check=False)
    _rr(result.returncode == 0, "GIT_READ_FAILED")
    _rr(len(result.stdout) <= 64 * 1024 * 1024, "GIT_OUTPUT_LIMIT")
    return result.stdout


def _rcontext(expected_main: str, *, env: Mapping[str, str] | None = None,
              verify: bool = False) -> dict[str, str]:
    env = os.environ if env is None else env
    _rr(re.fullmatch(r"[0-9a-f]{40}", expected_main), "EXPECTED_MAIN_REQUIRED")
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": RECOVERY_REPOSITORY,
        "GITHUB_REPOSITORY_ID": RECOVERY_REPOSITORY_ID, "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": RECOVERY_REPOSITORY + "/" + RECOVERY_WORKFLOW + "@refs/heads/main",
        "GITHUB_RUN_ATTEMPT": "1"}
    _rr(all(env.get(key) == value for key, value in expected.items()), "TRUSTED_WORKFLOW_CONTEXT_REQUIRED")
    _rr(env.get("GITHUB_SHA") == expected_main, "WORKFLOW_SOURCE_MAIN_MISMATCH")
    event = env.get("GITHUB_EVENT_NAME", "")
    _rr(event in {"workflow_dispatch", "schedule", "push"}, "EVENT_NOT_ALLOWED")
    if event in {"workflow_dispatch", "push"}:
        _rr(env.get("GITHUB_ACTOR") == RECOVERY_OWNER and env.get("GITHUB_TRIGGERING_ACTOR") == RECOVERY_OWNER
            and env.get("GITHUB_ACTOR_ID") == RECOVERY_OWNER_ID,
            "OWNER_ACTOR_REQUIRED")
    _rr(re.fullmatch(r"[1-9][0-9]{0,19}", env.get("GITHUB_RUN_ID", "")), "RUN_ID_REQUIRED")
    return {"run_id": env["GITHUB_RUN_ID"], "run_attempt": "1", "event": event,
        "head_sha": expected_main, "workflow_path": RECOVERY_WORKFLOW,
        "actor": env.get("GITHUB_ACTOR", ""), "actor_id": env.get("GITHUB_ACTOR_ID", ""),
        "triggering_actor": env.get("GITHUB_TRIGGERING_ACTOR", "")}


def _rsnapshot(root: pathlib.Path, commit: str, *, check_worktree: bool = True) -> tuple[str, dict[str, bytes]]:
    root = _rpath(root)
    _rr(re.fullmatch(r"[0-9a-f]{40}", commit), "INVALID_COMMIT")
    if check_worktree:
        _rr(_rgit(root, "rev-parse", "--verify", "HEAD").decode().strip() == commit, "HEAD_DRIFT")
        _rr(not _rgit(root, "status", "--porcelain=v1", "--untracked-files=normal"), "DIRTY_CHECKOUT")
    tree = _rgit(root, "rev-parse", commit + "^{tree}").decode().strip()
    entries = {}
    for raw in _rgit(root, "ls-tree", "-rz", "--full-tree", commit).split(b"\0"):
        if not raw:
            continue
        metadata, name = raw.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split(" ")
        name = name.decode("utf-8")
        _rr(cp.safe_repo_path(name) == name, "UNSAFE_TREE_PATH")
        entries[name] = (mode, kind, oid)
    fixed = {RECOVERY_HALT, RECOVERY_RECON, "state/EXECUTION_MODE.json", "state/AUTOPILOT_RUNTIME_MANIFEST.json",
        "state/MANUAL_MODE.md", "state/receipts/TASK107-R2.json", "tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json"}
    # Policy validation itself resolves and binds activation/owner paths; capture
    # all state and approval records too so no such authority input is omitted.
    names = {name for name in entries if name in fixed or name.startswith(RECOVERY_SCOPES)
        or name.startswith("state/") or name.startswith("tasks/approvals/")
        or name in cp.RUNTIME_PINNED_PATHS}
    data = {}
    for name in sorted(names):
        mode, kind, oid = entries[name]
        _rr(mode in {"100644", "100755"} and kind == "blob", "NONREGULAR_INPUT:" + name)
        payload = _rgit(root, "show", oid)
        _rr(len(payload) <= 16 * 1024 * 1024, "INPUT_SIZE")
        if check_worktree:
            _rr(_rread(root / name) == payload, "INPUT_BLOB_MISMATCH:" + name)
        data[name] = payload
    if check_worktree:
        for scope in RECOVERY_SCOPES:
            folder = _rpath(root / scope)
            disk = set()
            if folder.exists():
                _rr(folder.is_dir(), "INPUT_DIRECTORY_TYPE")
                for path in folder.rglob("*"):
                    _rpath(path)
                    if path.is_file():
                        disk.add(path.relative_to(root).as_posix())
            _rr(disk == {name for name in data if name.startswith(scope)}, "DIRECTORY_SET_DRIFT:" + scope)
    return tree, data


def _ridentity(data: Mapping[str, bytes], *, halt_required: bool = True) -> dict[str, str]:
    for path, expected in ((RECOVERY_RECON, RECOVERY_RECON_SHA), (RECOVERY_REQUEST, RECOVERY_REQUEST_SHA)):
        _rr(path in data and _rsha(data[path]) == expected, "IDENTITY_HASH:" + path)
    if halt_required:
        _rr(RECOVERY_HALT in data and _rsha(data[RECOVERY_HALT]) == RECOVERY_HALT_SHA, "HALT_IDENTITY")
    recon = _robject(data[RECOVERY_RECON])
    _rr(recon.get("semantic_outcome") == "ABORTED_NO_PRODUCTION_WRITE"
        and recon.get("original_run_id") == RECOVERY_FAILED_RUN
        and recon.get("transaction_path") == RECOVERY_TRANSACTION
        and recon.get("halt_snapshot", {}).get("sha256") == RECOVERY_HALT_SHA, "RECONCILIATION_IDENTITY")
    anchors = recon.get("state_anchors", {})
    _rr(anchors.get("terminal_transaction_sha256") == _rsha(data.get(RECOVERY_TRANSACTION, b""))
        and anchors.get("terminal_claim_sha256") == _rsha(data.get(RECOVERY_CLAIM, b"")), "TERMINAL_IDENTITY")
    tx, claim, ledger = (_robject(data[path]) for path in (RECOVERY_TRANSACTION, RECOVERY_CLAIM, RECOVERY_LEDGER))
    _rr(tx.get("status") == "ROLLED_BACK" and tx.get("run_id") == RECOVERY_FAILED_RUN
        and tx.get("request_sha256") == RECOVERY_REQUEST_SHA
        and tx.get("transaction_id") == "tx-" + RECOVERY_FAILED_RUN + "-" + RECOVERY_REQUEST_SHA[:16]
        and claim.get("task_execution_status") == "FAILED"
        and ledger.get("task_id") == RECOVERY_FAILED_TASK and ledger.get("request_sha256") == RECOVERY_REQUEST_SHA,
        "TERMINAL_RECORD_BINDING")
    return {"failed_task": RECOVERY_FAILED_TASK, "failed_run": RECOVERY_FAILED_RUN,
            "halt_sha256": RECOVERY_HALT_SHA, "request_sha256": RECOVERY_REQUEST_SHA,
            "reconciliation_sha256": RECOVERY_RECON_SHA, "mode_epoch": RECOVERY_EPOCH}


def _rdurable(data: Mapping[str, bytes], now: dt.datetime) -> dict[str, int]:
    counts = {"terminal_claims": 0, "terminal_transactions": 0, "expired_auto_launches": 0}
    for name, payload in data.items():
        if name.startswith("state/claims/"):
            _rr(_robject(payload).get("task_execution_status") in {"FINISHED", "FAILED", "ROLLED_BACK"}, "ACTIVE_CLAIM:" + name)
            counts["terminal_claims"] += 1
        elif name.startswith("state/transactions/"):
            _rr(_robject(payload).get("status") in {"FINISHED", "ROLLED_BACK"}, "PENDING_TRANSACTION:" + name)
            counts["terminal_transactions"] += 1
        elif name.startswith("tasks/launch/AUTO-"):
            value = _robject(payload)
            _rr(value.get("schema_version") == "UA-ART-AUTOSTART-LAUNCH-1", "UNKNOWN_AUTO_LAUNCH")
            _rr(_rtime(value.get("expires_at")) <= now, "UNEXPIRED_AUTO_LAUNCH:" + name)
            counts["expired_auto_launches"] += 1
    return counts


def _rqueue(queue_dir: pathlib.Path, root: pathlib.Path, expected: str,
            context: Mapping[str, str], now: dt.datetime) -> dict[str, Any]:
    queue_dir, root = _rpath(queue_dir), _rpath(root)
    _rr(queue_dir != root and root not in queue_dir.parents, "QUEUE_MUST_BE_OUTSIDE_CHECKOUT")
    metadata = _robject(_rread(queue_dir / "metadata.json"))
    _rr(metadata.get("schema_version") == "UA-ART-RECOVERY-QUEUE-CAPTURE-1"
        and metadata.get("repository") == RECOVERY_REPOSITORY
        and metadata.get("expected_main") == expected
        and str(metadata.get("run_id")) == context["run_id"], "QUEUE_CAPTURE_BINDING")
    start, end = (_rtime(metadata.get(key)) for key in ("capture_started_at", "capture_finished_at"))
    _rr(start <= end <= now and 0 <= (now - start).total_seconds() <= 120, "STALE_QUEUE")
    hashes, self_seen = {}, False
    for status in RECOVERY_QUEUE_STATUSES:
        payload = _rread(queue_dir / (status + ".json"))
        hashes[status] = _rsha(payload)
        pages = _rjson(payload)
        _rr(isinstance(pages, list) and bool(pages) and len(pages) <= 100, "QUEUE_PAGINATION")
        runs, total = [], None
        for page in pages:
            _rr(isinstance(page, dict) and type(page.get("total_count")) is int
                and isinstance(page.get("workflow_runs"), list), "QUEUE_PAGE_SCHEMA")
            if total is None:
                total = page["total_count"]
            _rr(total == page["total_count"] and 0 <= len(page["workflow_runs"]) <= 100, "QUEUE_PAGE_COUNT")
            runs.extend(page["workflow_runs"])
        _rr(len(runs) == total and len({run.get("id") for run in runs}) == total, "QUEUE_PAGINATION_INCOMPLETE")
        for run in runs:
            actor = run.get("actor", {}).get("login")
            trigger = run.get("triggering_actor", {}).get("login")
            _rr(str(run.get("id")) == context["run_id"] and not self_seen
                and run.get("path") == RECOVERY_WORKFLOW and run.get("head_sha") == expected
                and run.get("head_branch") == "main" and run.get("event") == context["event"]
                and run.get("run_attempt") == 1 and run.get("status") == status
                and str(run.get("repository", {}).get("id")) == RECOVERY_REPOSITORY_ID
                and run.get("repository", {}).get("full_name") == RECOVERY_REPOSITORY
                and (context["event"] not in {"workflow_dispatch", "push"} or actor == trigger == RECOVERY_OWNER
                    and str(run.get("actor", {}).get("id")) == RECOVERY_OWNER_ID
                    and str(run.get("triggering_actor", {}).get("id")) == RECOVERY_OWNER_ID),
                "ACTIVE_OR_UNTRUSTED_ACTION_RUN")
            self_seen = True
    _rr(self_seen, "CURRENT_RUN_NOT_OBSERVED")
    return {"status": "EMPTY_EXCEPT_THIS_TRUSTED_RUN", "captured_at": end.isoformat(),
            "capture_sha256": _rsha(_rcanonical(metadata)), "raw_sha256": hashes,
            "current_run_observed": self_seen, "maximum_age_seconds": 120}


def _rcode(data: Mapping[str, bytes]) -> dict[str, str]:
    return {name: _rsha(data[name]) for name in sorted(cp.RUNTIME_PINNED_PATHS)}


def _rcanary(root: pathlib.Path, data: Mapping[str, bytes], current: str) -> dict[str, Any]:
    _rr(RECOVERY_CANARY in data, "VERIFIED_CANARY_REQUIRED")
    receipt = _robject(data[RECOVERY_CANARY])
    _rr(receipt.get("schema_version") == "UA-ART-RECOVERY-ROUTE-CANARY-1"
        and receipt.get("task_id") == RECOVERY_TASK and receipt.get("repository") == RECOVERY_REPOSITORY
        and receipt.get("halt_sha256") == RECOVERY_HALT_SHA
        and receipt.get("reconciliation_sha256") == RECOVERY_RECON_SHA
        and receipt.get("runtime_hashes") == _rcode(data)
        and receipt.get("runtime_manifest_sha256") == _rsha(data["state/AUTOPILOT_RUNTIME_MANIFEST.json"])
        and receipt.get("halt_removed") is False and receipt.get("application_writes") == 0,
        "CANARY_RECEIPT_BINDING")
    base = receipt.get("parent_commit", "")
    _rr(re.fullmatch(r"[0-9a-f]{40}", base), "CANARY_PARENT")
    history = _rgit(root, "log", "--format=%H", "--full-history", current, "--", RECOVERY_CANARY).decode().splitlines()
    _rr(len(history) == 1 and re.fullmatch(r"[0-9a-f]{40}", history[0]), "CANARY_IMMUTABLE_HISTORY_REQUIRED")
    addition = history[0]
    parents = _rgit(root, "show", "-s", "--format=%P", addition).decode().strip().split()
    _rr(parents == [base], "CANARY_PARENT_BINDING")
    changes = _rgit(root, "diff-tree", "--no-commit-id", "--name-status", "-r", base, addition).decode().splitlines()
    _rr(changes == ["A\t" + RECOVERY_CANARY], "CANARY_ATOMIC_WRITE_SCOPE")
    _rr(_rgit(root, "show", addition + ":" + RECOVERY_CANARY) == data[RECOVERY_CANARY]
        and _rsha(_rgit(root, "show", base + ":" + RECOVERY_HALT)) == RECOVERY_HALT_SHA
        and _rsha(_rgit(root, "show", addition + ":" + RECOVERY_HALT)) == RECOVERY_HALT_SHA,
        "CANARY_READBACK_IDENTITY")
    return {"status": "VERIFIED_IMMUTABLE_GIT_COMMIT", "commit": addition,
            "receipt_sha256": _rsha(data[RECOVERY_CANARY])}


def _rplan(expected_main: str, tree: str, data: Mapping[str, bytes]) -> dict[str, Any]:
    return {"schema_version": "UA-ART-RECOVERY-ROUTE-PLAN-1", "task_id": RECOVERY_TASK,
        "repository": RECOVERY_REPOSITORY, "parent_commit": expected_main, "parent_tree": tree,
        "identity": _ridentity(data),
        "input_hashes": {name: _rsha(payload) for name, payload in sorted(data.items())},
        "runtime_hashes": _rcode(data),
        "runtime_manifest_sha256": _rsha(data["state/AUTOPILOT_RUNTIME_MANIFEST.json"]),
        "writer_group": "ua-art-production-writer", "scope": "TASK120_HALT_ONLY_NO_APPLICATION_WRITES",
        "required_owner_command_prefix": "СНЯТЬ HALT " + RECOVERY_TASK + " "}


def _rexternal_writers_verified() -> None:
    # Stage A explicitly identified external PythonAnywhere writer activity as
    # unverified. Registration and its one-file canary do not require an app
    # credential, but opening production execution must not silently discard
    # that blocker. There is intentionally no command-line/env bypass. A future
    # reviewed adapter must obtain current authenticated external writer proof.
    raise WatchdogError("RECOVERY_EXTERNAL_WRITER_VERIFICATION_REQUIRED")


def recovery_proposal(command: str, expected_main: str, queue_dir: pathlib.Path | None, *,
                      root: pathlib.Path = ROOT, env: Mapping[str, str] | None = None,
                      now: dt.datetime | None = None, plan_sha256: str = "",
                      owner_confirmation: str = "") -> tuple[dict[str, Any], dict[str, bytes]]:
    """Construct a proposal; never change repository data or contact a service."""
    _rr(command in {"recovery-plan", "recovery-canary", "recovery-execute"}, "INVALID_COMMAND")
    now = now or dt.datetime.now(dt.timezone.utc)
    context = _rcontext(expected_main, env=env)
    _rr(command == "recovery-canary" or context["event"] == "workflow_dispatch", "SCHEDULE_CANARY_ONLY")
    tree, data = _rsnapshot(root, expected_main)
    policy = cp.verify_execution_mode(root=root, required_mode="AUTOMATIC", allow_halt_for_recovery=True)
    _rr(policy.get("status") == "PASS" and policy.get("mode_epoch") == RECOVERY_EPOCH, "PINNED_POLICY_REQUIRED")
    # An immutable prior canary remains a successful NOOP after eventual HALT
    # removal; it never writes a second receipt or invents a new recovery.
    if command == "recovery-canary" and RECOVERY_CANARY in data:
        proof = _rcanary(root, data, expected_main)
        return {"schema_version": "UA-ART-RECOVERY-ROUTE-PROPOSAL-1", "task_id": RECOVERY_TASK,
            "operation": "NOOP", "ready": False, "parent_commit": expected_main, "parent_tree": tree,
            "changes": [], "canary": proof, "application_writes": 0}, {}
    identity = _ridentity(data)
    _rr(RECOVERY_ARCHIVE not in data and RECOVERY_RECEIPT not in data, "RECOVERY_ALREADY_RECORDED")
    durable = _rdurable(data, now)
    _rr(queue_dir is not None, "QUEUE_REQUIRED")
    queue = _rqueue(queue_dir, root, expected_main, context, now)
    hashes = {name: _rsha(payload) for name, payload in sorted(data.items())}
    semantic = _rplan(expected_main, tree, data)
    plan_hash = _rsha(_rcanonical(semantic))
    proposal = {"schema_version": "UA-ART-RECOVERY-ROUTE-PROPOSAL-1", "task_id": RECOVERY_TASK,
        "operation": "PLAN", "ready": False, "parent_commit": expected_main, "parent_tree": tree,
        "plan_sha256": plan_hash, "plan": semantic, "input_hashes": hashes, "context": context,
        "queue": queue, "durable_queue": durable, "changes": [], "application_writes": 0,
        "recorded_at": now.isoformat(), "live_write_verified": False,
        "execution_ready": False, "execution_blockers": ["EXTERNAL_WRITER_VERIFICATION_REQUIRED", "SEPARATE_OWNER_COMMAND_REQUIRED"]}
    outputs: dict[str, bytes] = {}
    if command == "recovery-canary":
        receipt = {"schema_version": "UA-ART-RECOVERY-ROUTE-CANARY-1", "task_id": RECOVERY_TASK,
            "repository": RECOVERY_REPOSITORY, "parent_commit": expected_main,
            "plan_sha256": plan_hash, "halt_sha256": RECOVERY_HALT_SHA,
            "reconciliation_sha256": RECOVERY_RECON_SHA,
            "runtime_hashes": semantic["runtime_hashes"], "runtime_manifest_sha256": semantic["runtime_manifest_sha256"],
            "context": context, "recorded_at": now.isoformat(), "halt_removed": False,
            "application_writes": 0, "evidence_scope": "COMMIT_PRESENCE_AND_SEPARATE_READBACK_REQUIRED"}
        outputs["receipt.json"] = _rcanonical(receipt) + b"\n"
        proposal.update(operation="CANARY", ready=True, changes=[{"operation": "add", "path": RECOVERY_CANARY,
            "source": "receipt.json", "content_sha256": _rsha(outputs["receipt.json"]), "must_not_exist": True}])
    elif command == "recovery-execute":
        _rr(plan_sha256 == plan_hash and re.fullmatch(r"[0-9a-f]{64}", plan_sha256), "PLAN_APPROVAL_MISMATCH")
        _rr(owner_confirmation == "СНЯТЬ HALT " + RECOVERY_TASK + " " + plan_hash, "SEPARATE_OWNER_COMMAND_REQUIRED")
        proof = _rcanary(root, data, expected_main)
        _rexternal_writers_verified()
        receipt = {"schema_version": "UA-ART-RECOVERY-ROUTE-EXECUTION-1", "task_id": RECOVERY_TASK,
            "repository": RECOVERY_REPOSITORY, "parent_commit": expected_main, "plan_sha256": plan_hash,
            "owner_confirmation": owner_confirmation, "context": context, "recorded_at": now.isoformat(),
            "halt_sha256": RECOVERY_HALT_SHA, "archive_path": RECOVERY_ARCHIVE,
            "reconciliation_sha256": RECOVERY_RECON_SHA, "semantic_outcome": "ABORTED_NO_PRODUCTION_WRITE",
            "canary": proof, "input_hashes": hashes, "application_writes": 0,
            "evidence_scope": "COMMIT_PRESENCE_AND_SEPARATE_READBACK_REQUIRED"}
        outputs.update({"receipt.json": _rcanonical(receipt) + b"\n", "halt.json": data[RECOVERY_HALT]})
        proposal.update(operation="EXECUTE", ready=True, changes=[
            {"operation": "delete", "path": RECOVERY_HALT, "expected_sha256": RECOVERY_HALT_SHA},
            {"operation": "add", "path": RECOVERY_ARCHIVE, "source": "halt.json", "content_sha256": RECOVERY_HALT_SHA, "must_not_exist": True},
            {"operation": "add", "path": RECOVERY_RECEIPT, "source": "receipt.json", "content_sha256": _rsha(outputs["receipt.json"]), "must_not_exist": True}])
    _rr(_rsnapshot(root, expected_main) == (tree, data), "INPUT_CHANGED_DURING_PREFLIGHT")
    return proposal, outputs


def recovery_verify(proposal: Mapping[str, Any], result_commit: str, expected_main: str, *,
                    root: pathlib.Path = ROOT, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    context = _rcontext(expected_main, env=env, verify=True)
    _rr(proposal.get("schema_version") == "UA-ART-RECOVERY-ROUTE-PROPOSAL-1"
        and proposal.get("task_id") == RECOVERY_TASK and proposal.get("parent_commit") == expected_main
        and proposal.get("context") == context and proposal.get("ready") is True, "PROPOSAL_BINDING")
    _rr(re.fullmatch(r"[0-9a-f]{40}", result_commit), "RESULT_COMMIT_REQUIRED")
    parents = _rgit(root, "show", "-s", "--format=%P", result_commit).decode().strip().split()
    _rr(parents == [expected_main], "RESULT_PARENT_MISMATCH")
    before_tree, before = _rsnapshot(root, expected_main, check_worktree=False)
    after_tree, after = _rsnapshot(root, result_commit, check_worktree=False)
    _rr(proposal.get("parent_tree") == before_tree
        and proposal.get("input_hashes") == {name: _rsha(payload) for name, payload in sorted(before.items())}, "RESULT_INPUT_BINDING")
    plan = proposal.get("plan", {})
    _rr(plan == _rplan(expected_main, before_tree, before)
        and proposal.get("plan_sha256") == _rsha(_rcanonical(plan)), "RESULT_PLAN_HASH")
    operation = proposal.get("operation")
    expected_changes = {RECOVERY_CANARY: "A"} if operation == "CANARY" else {
        RECOVERY_HALT: "D", RECOVERY_ARCHIVE: "A", RECOVERY_RECEIPT: "A"} if operation == "EXECUTE" else {}
    _rr(bool(expected_changes), "RESULT_OPERATION")
    actual = {}
    for line in _rgit(root, "diff-tree", "--no-commit-id", "--name-status", "-r", expected_main, result_commit).decode().splitlines():
        status, path = line.split("\t", 1)
        actual[path] = status
    _rr(actual == expected_changes, "RESULT_WRITE_SCOPE")
    changes = proposal.get("changes", [])
    _rr(isinstance(changes, list) and len(changes) == len(expected_changes)
        and {item.get("path") for item in changes} == set(expected_changes), "RESULT_PROPOSAL_SCOPE")
    for item in changes:
        path = item["path"]
        if expected_changes[path] == "D":
            _rr(item.get("operation") == "delete" and path not in after
                and _rsha(before[path]) == item.get("expected_sha256") == RECOVERY_HALT_SHA, "RESULT_DELETE_IDENTITY")
        else:
            _rr(item.get("operation") == "add" and item.get("must_not_exist") is True
                and path not in before and path in after and _rsha(after[path]) == item.get("content_sha256"), "RESULT_ADD_IDENTITY")
    _rr(all(after.get(name) == payload for name, payload in before.items() if name not in expected_changes), "RESULT_PRESERVED_INPUT_CHANGED")
    if operation == "CANARY":
        _rcanary(root, after, result_commit)
        _rr(_robject(after[RECOVERY_CANARY]).get("context") == context, "RESULT_CANARY_CONTEXT")
        _rr(after.get(RECOVERY_HALT) == before.get(RECOVERY_HALT), "RESULT_HALT_CHANGED")
    else:
        receipt = _robject(after[RECOVERY_RECEIPT])
        _rr(after.get(RECOVERY_ARCHIVE) == before.get(RECOVERY_HALT)
            and receipt.get("schema_version") == "UA-ART-RECOVERY-ROUTE-EXECUTION-1"
            and receipt.get("task_id") == RECOVERY_TASK and receipt.get("context") == context
            and receipt.get("parent_commit") == expected_main and receipt.get("plan_sha256") == proposal.get("plan_sha256")
            and receipt.get("owner_confirmation") == "СНЯТЬ HALT " + RECOVERY_TASK + " " + proposal["plan_sha256"],
            "RESULT_EXECUTION_RECEIPT")
    return {"schema_version": "UA-ART-RECOVERY-ROUTE-VERIFICATION-1", "task_id": RECOVERY_TASK,
        "operation": "VERIFIED", "verified_operation": operation, "ready": False, "status": "PASS",
        "parent_commit": expected_main, "result_commit": result_commit, "result_tree": after_tree,
        "git_commit_verified": True, "live_write_verified": False, "remote_readback_required": True,
        "application_writes": 0, "changes": sorted(expected_changes)}


def _rwrite_output(directory: pathlib.Path, root: pathlib.Path, proposal: Mapping[str, Any],
                   payloads: Mapping[str, bytes]) -> None:
    directory, root = _rpath(directory), _rpath(root)
    _rr(directory != root and root not in directory.parents and directory.parent.is_dir(), "OUTPUT_MUST_BE_OUTSIDE_CHECKOUT")
    _rr(not directory.exists(), "OUTPUT_ALREADY_EXISTS")
    directory.mkdir(mode=0o700)
    files = {"proposal.json": _rcanonical(proposal) + b"\n", "report.json": _rcanonical(proposal) + b"\n", **payloads}
    for name, payload in files.items():
        _rr(name in {"proposal.json", "report.json", "receipt.json", "halt.json"}, "OUTPUT_FILE_SCOPE")
        with os.fdopen(os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    _output({"ready": str(proposal.get("ready", False)).lower(), "operation": proposal["operation"],
        "parent_commit": proposal["parent_commit"], "plan_sha256": proposal.get("plan_sha256", ""),
        "receipt_sha256": _rsha(payloads["receipt.json"]) if "receipt.json" in payloads else "",
        "halt_sha256": RECOVERY_HALT_SHA, "proposal_sha256": _rsha(files["proposal.json"])})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("discover", "assert-clear", "recovery-plan", "recovery-canary", "recovery-execute", "recovery-verify"))
    parser.add_argument("--expected-main", default="")
    parser.add_argument("--queue-dir", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--plan-sha256", default="")
    parser.add_argument("--owner-confirmation", default="")
    parser.add_argument("--proposal", type=pathlib.Path)
    parser.add_argument("--result-commit", default="")
    args = parser.parse_args()
    if args.command.startswith("recovery-"):
        _rr(args.output is not None, "OUTPUT_REQUIRED")
        if args.command == "recovery-verify":
            _rr(args.proposal is not None, "PROPOSAL_REQUIRED")
            result = recovery_verify(_robject(_rread(args.proposal)), args.result_commit, args.expected_main)
            payloads = {}
        else:
            result, payloads = recovery_proposal(args.command, args.expected_main, args.queue_dir,
                plan_sha256=args.plan_sha256, owner_confirmation=args.owner_confirmation)
        _rwrite_output(args.output, ROOT, result, payloads)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    result = discover() if args.command == "discover" else assert_clear()
    _output(_github_outputs(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
