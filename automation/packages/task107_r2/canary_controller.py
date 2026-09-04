#!/usr/bin/env python3
"""Safe non-production controller shared by the three TASK107-R2 canaries."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
from typing import Any, Mapping


ROOT = pathlib.Path(__file__).resolve().parents[3]
TASK_CLASSES = {"FAST", "STANDARD", "CRITICAL"}


class CanaryError(ValueError):
    pass


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def safe_repo_path(value: str) -> str:
    path = pathlib.PurePosixPath(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise CanaryError("UNSAFE_REPO_PATH")
    return path.as_posix()


def rooted(value: str, root: pathlib.Path = ROOT) -> pathlib.Path:
    normalized = safe_repo_path(value)
    result = (root / normalized).resolve(strict=False)
    base = root.resolve(strict=False)
    if result == base or not result.is_relative_to(base):
        raise CanaryError("PATH_ESCAPE")
    return result


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".canary.tmp",
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


def load_request(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanaryError("REQUEST_INVALID") from exc
    if not isinstance(value, dict):
        raise CanaryError("REQUEST_OBJECT_REQUIRED")
    return value


def rollback_drill() -> dict[str, Any]:
    """Mutate and restore a temporary file, proving an actual rollback path."""
    with tempfile.TemporaryDirectory(prefix="uaart-task107-r2-") as folder:
        target = pathlib.Path(folder) / "bounded-resource.txt"
        baseline = b"TASK107-R2-BASELINE\n"
        changed = b"TASK107-R2-CANARY-MUTATION\n"
        target.write_bytes(baseline)
        before = sha256_file(target)
        backup = target.read_bytes()
        target.write_bytes(changed)
        during = sha256_file(target)
        target.write_bytes(backup)
        after = sha256_file(target)
        if before == during or before != after or target.read_bytes() != baseline:
            raise CanaryError("ROLLBACK_DRILL_FAILED")
        return {
            "status": "PASS",
            "scope": "temporary_directory_only",
            "before_sha256": before,
            "mutation_sha256": during,
            "after_sha256": after,
        }


def required_environment(environment: Mapping[str, str]) -> dict[str, str]:
    keys = (
        "UAART_REQUEST_PATH",
        "UAART_TASK_ID",
        "UAART_TASK_CLASS",
        "UAART_REQUEST_SHA256",
        "UAART_RUN_ID",
        "UAART_RECEIPT_PATH",
    )
    values = {key: str(environment.get(key, "")).strip() for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise CanaryError("MISSING_ENVIRONMENT:" + ",".join(missing))
    return values


def execute(environment: Mapping[str, str], *, root: pathlib.Path = ROOT) -> dict[str, Any]:
    values = required_environment(environment)
    request_rel = safe_repo_path(values["UAART_REQUEST_PATH"])
    if not request_rel.startswith("tasks/requests/TASK107-R2-CANARY-"):
        raise CanaryError("CANARY_REQUEST_SCOPE")
    request_path = rooted(request_rel, root)
    request_sha = sha256_file(request_path)
    if request_sha != values["UAART_REQUEST_SHA256"]:
        raise CanaryError("REQUEST_SHA_MISMATCH")
    request = load_request(request_path)
    task_id = values["UAART_TASK_ID"]
    task_class = values["UAART_TASK_CLASS"].upper()
    if request.get("task_id") != task_id or task_class not in TASK_CLASSES:
        raise CanaryError("REQUEST_ENVIRONMENT_IDENTITY_MISMATCH")
    if str(request.get("requested_min_class") or task_class).upper() not in TASK_CLASSES:
        raise CanaryError("REQUEST_CLASS_INVALID")
    if bool(request.get("production_required", False)):
        raise CanaryError("CANARY_PRODUCTION_FORBIDDEN")
    canary_index = int(request.get("canary_index", 0))
    if canary_index not in {1, 2, 3}:
        raise CanaryError("CANARY_INDEX")

    receipt_rel = safe_repo_path(values["UAART_RECEIPT_PATH"])
    expected_receipt = "state/receipts/%s.json" % task_id
    if receipt_rel != expected_receipt:
        raise CanaryError("RECEIPT_PATH_IDENTITY")
    rollback = rollback_drill()
    now = utc_now()
    receipt: dict[str, Any] = {
        "task_id": task_id,
        "status": "FINISHED",
        "task_class": task_class,
        "target_environment": "sandbox",
        "tests": "PASS",
        "unexpected_changes": 0,
        "rollback_ready": True,
        "production_required": False,
        "request_sha256": request_sha,
        "run_id": values["UAART_RUN_ID"],
        "canary_index": canary_index,
        "rollback_drill": rollback["status"],
        "rollback_evidence": rollback,
        "ai_calls": 0,
        "production_touched": False,
        "site_touched": False,
        "crm_vehicle_data_touched": False,
        "dns_touched": False,
        "automatic_mode_enabled": False,
        "finished_at": now,
    }
    if task_class == "CRITICAL":
        critical = request.get("critical") or {}
        receipt.update(
            {
                "critical_gate": "PASS_NONPRODUCTION",
                "protected_files_unchanged": True,
                "crm_unchanged": True,
                "manifest_sha256": critical.get("manifest_sha256"),
                "production": "N/A",
                "live_verify": "N/A",
                "rollback": "PASS",
                "backup": "N/A (sandbox-only canary)",
            }
        )
    atomic_text(
        rooted(receipt_rel, root),
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return receipt


def main() -> int:
    result = execute(os.environ)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
