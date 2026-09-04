#!/usr/bin/env python3
"""Discover and validate one durable orphaned Production transaction.

The workflow using this module shares the global Production concurrency key,
so an OPEN record can be recovered only after its original writer job ended.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
from typing import Any

import control_plane as cp


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_KEYS = {
    "autostart_ledger_path",
    "backup_manifest_sha256",
    "backup_receipt_path",
    "backup_receipt_sha256",
    "expires_at",
    "mode_epoch",
    "opened_at",
    "request_path",
    "request_sha256",
    "run_id",
    "schema_version",
    "status",
    "task_id",
    "transaction_id",
}


class WatchdogError(ValueError):
    pass


def _output(values: dict[str, Any]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            text = str(value)
            if "\n" in text or "\r" in text:
                raise WatchdogError("MULTILINE_OUTPUT:" + key)
            handle.write(f"{key}={text}\n")


def validate_transaction(path: pathlib.Path, *, root: pathlib.Path = ROOT) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise WatchdogError("TRANSACTION_FILE_INVALID")
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise WatchdogError("TRANSACTION_OUTSIDE_ROOT") from exc
    if not relative.startswith("state/transactions/") or not relative.endswith(".json"):
        raise WatchdogError("TRANSACTION_PATH_SCOPE")
    value = cp.read_json(path)
    if set(value) != EXPECTED_KEYS:
        raise WatchdogError("TRANSACTION_SCHEMA_KEYS")
    if value.get("schema_version") != cp.PRODUCTION_TRANSACTION_SCHEMA:
        raise WatchdogError("TRANSACTION_SCHEMA")
    if value.get("status") != "OPEN":
        raise WatchdogError("TRANSACTION_NOT_OPEN")
    request_rel = cp.safe_repo_path(str(value.get("request_path", "")))
    request_path = cp.repo_path(request_rel, root)
    if request_path.is_symlink() or not request_path.is_file():
        raise WatchdogError("TRANSACTION_REQUEST_MISSING")
    if cp.sha256_file(request_path) != cp.require_sha(value.get("request_sha256"), "request"):
        raise WatchdogError("TRANSACTION_REQUEST_SHA")
    request = cp.read_json(request_path)
    if request.get("task_id") != value.get("task_id"):
        raise WatchdogError("TRANSACTION_TASK_ID")
    if request.get("production_required") is not True:
        raise WatchdogError("TRANSACTION_NOT_PRODUCTION")
    execution = request.get("execution")
    if not isinstance(execution, dict):
        raise WatchdogError("TRANSACTION_EXECUTION_OBJECT")
    if execution.get("backup_receipt_path") != value.get("backup_receipt_path"):
        raise WatchdogError("TRANSACTION_BACKUP_RECEIPT_BINDING")
    cp.require_sha(value.get("backup_manifest_sha256"), "backup_manifest")
    cp.require_sha(value.get("backup_receipt_sha256"), "backup_receipt")
    cp.parse_utc(str(value.get("opened_at", "")))
    cp.parse_utc(str(value.get("expires_at", "")))
    if not re.fullmatch(r"tx-[A-Za-z0-9._-]{16,120}", str(value.get("transaction_id", ""))):
        raise WatchdogError("TRANSACTION_ID")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(value.get("run_id", ""))):
        raise WatchdogError("TRANSACTION_RUN_ID")
    return value | {"transaction_path": relative}


def discover(*, root: pathlib.Path = ROOT) -> dict[str, Any]:
    folder = root / "state/transactions"
    if not folder.is_dir():
        return {"has_pending": False}
    pending = []
    for path in sorted(folder.glob("*.json")):
        value = cp.read_json(path)
        if value.get("status") == "OPEN":
            pending.append(validate_transaction(path, root=root))
    if not pending:
        return {"has_pending": False}
    result = dict(pending[0])
    result["has_pending"] = True
    result["pending_count"] = len(pending)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("discover",))
    args = parser.parse_args()
    if args.command == "discover":
        result = discover()
        _output({
            "has_pending": str(result["has_pending"]).lower(),
            **({
                "backup_manifest_sha256": result["backup_manifest_sha256"],
                "request_path": result["request_path"],
                "request_sha256": result["request_sha256"],
                "run_id": result["run_id"],
                "task_id": result["task_id"],
                "transaction_id": result["transaction_id"],
                "transaction_path": result["transaction_path"],
            } if result["has_pending"] else {}),
        })
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
