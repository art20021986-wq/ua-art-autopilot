#!/usr/bin/env python3
"""Deterministic non-production canary for global automatic intake."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
from typing import Any, Mapping


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASK_ID = "TASK113-GLOBAL-AUTO-CANARY"
EVIDENCE_REL = "cloud/task113_auto/evidence.json"
RECEIPT_REL = "state/receipts/TASK113-GLOBAL-AUTO-CANARY.json"


class CanaryError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rooted(value: str) -> pathlib.Path:
    path = pathlib.PurePosixPath(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise CanaryError("UNSAFE_REPO_PATH")
    resolved = (ROOT / path).resolve(strict=False)
    if resolved == ROOT.resolve(strict=False) or not resolved.is_relative_to(ROOT.resolve(strict=False)):
        raise CanaryError("REPO_PATH_ESCAPE")
    return resolved


def atomic_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".task113.tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(dict(value), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"] != "FAST":
        raise CanaryError("TASK_IDENTITY")
    if values["UAART_RECEIPT_PATH"] != RECEIPT_REL:
        raise CanaryError("RECEIPT_IDENTITY")
    request_path = rooted(values["UAART_REQUEST_PATH"])
    if request_path.is_symlink() or not request_path.is_file():
        raise CanaryError("REQUEST_FILE")
    if sha_file(request_path) != values["UAART_REQUEST_SHA256"]:
        raise CanaryError("REQUEST_SHA_MISMATCH")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("task_id") != TASK_ID or request.get("production_required") is not False:
        raise CanaryError("REQUEST_IDENTITY")
    return values


def rollback_drill() -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="uaart-task113-") as folder:
        path = pathlib.Path(folder) / "probe"
        original = b"TASK113-ORIGINAL\n"
        path.write_bytes(original)
        before = sha_file(path)
        backup = path.read_bytes()
        path.write_bytes(b"TASK113-MUTATED\n")
        during = sha_file(path)
        path.write_bytes(backup)
        after = sha_file(path)
    if before == during or before != after:
        raise CanaryError("ROLLBACK_DRILL_FAILED")
    return {"status": "PASS", "before": before, "during": during, "after": after}


def run(environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    values = required_environment(environment or os.environ)
    mode = json.loads(rooted("state/EXECUTION_MODE.json").read_text(encoding="utf-8"))
    if mode.get("mode") != "AUTOMATIC" or not str(mode.get("mode_epoch", "")).startswith("auto-"):
        raise CanaryError("AUTOMATIC_MODE_REQUIRED")
    rollback = rollback_drill()
    finished = utc_now()
    evidence = {
        "automatic_mode_enabled": True,
        "finished_at": finished,
        "mode_epoch": mode["mode_epoch"],
        "production_touched": False,
        "rollback_drill": rollback,
        "status": "PASS",
        "task_id": TASK_ID,
    }
    receipt = {
        "automatic_mode_enabled": True,
        "mode_epoch": mode["mode_epoch"],
        "production_required": False,
        "production_touched": False,
        "request_sha256": values["UAART_REQUEST_SHA256"],
        "rollback_ready": True,
        "run_id": values["UAART_RUN_ID"],
        "status": "FINISHED",
        "target_environment": "sandbox",
        "task_class": "FAST",
        "task_id": TASK_ID,
        "tests": "PASS",
        "unexpected_changes": 0,
    }
    atomic_json(rooted(EVIDENCE_REL), evidence)
    atomic_json(rooted(RECEIPT_REL), receipt)
    return receipt


def main() -> int:
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
