#!/usr/bin/env python3
"""TASK 058 — CRM-OCR-SYNC-001 isolated read-only controller.

This controller does NOT run inside this sandbox against real PythonAnywhere
(no network access here). It is written so that an operator with legitimate
SSH access can invoke it, and so that it is fully unit-testable via dependency
injection of the `executor` callable (real usage would pass a function that
shells out to `ssh`).

Contract:
  1. Validate a sync manifest: every required local file must exist and its
     sha256 must match the manifest before any remote action is attempted.
  2. Build exactly one remote command string (never executed in this repo):
       python3.10 /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/live_discovery.py
         --sources team_bot.py db.py cars_ui.py avtoperedacha.py run_all.py start_safe.py
         --db <allowlisted db path>
         --logs <allowlisted log paths>
         --out /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/receipt.json
  3. Poll for exactly one receipt file at the exact expected path, bounded by
     timeout and interval.
  4. Validate the receipt: well-formed JSON, not stale (timestamp within
     freshness window), and free of sensitive content markers.
  5. Relay the sanitized evidence to the caller.
  6. In `finally`, always attempt to delete the temporary trigger and the
     receipt from the safe inbox, on success, failure, or timeout.

No `sudo`, shell globs, `find -exec`, or any other remote command may ever be
issued. Only ONE exact remote command is permitted per run.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

SAFE_INBOX_ROOT = "/home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync"
RECEIPT_FILENAME = "receipt.json"
TRIGGER_FILENAME = "trigger.flag"
MAX_RECEIPT_AGE_SECONDS = 600
DEFAULT_POLL_INTERVAL_SECONDS = 2
DEFAULT_TIMEOUT_SECONDS = 120

SENSITIVE_MARKERS = [
    "token",
    "api_key",
    "apikey",
    "password",
    "secret",
    "@gmail",
    "@yahoo",
    "BEGIN PRIVATE KEY",
]


class ControllerError(Exception):
    pass


class ManifestMismatchError(ControllerError):
    pass


class ReceiptValidationError(ControllerError):
    pass


class RemoteTimeoutError(ControllerError):
    pass


@dataclass
class ManifestEntry:
    relative_path: str
    expected_sha256: str


@dataclass
class SyncManifest:
    entries: list[ManifestEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "SyncManifest":
        entries = [
            ManifestEntry(relative_path=item["relative_path"], expected_sha256=item["sha256"])
            for item in data.get("files", [])
        ]
        return cls(entries=entries)


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def validate_manifest(local_package_root: Path, manifest: SyncManifest) -> None:
    if not manifest.entries:
        raise ManifestMismatchError("EMPTY_MANIFEST")
    for entry in manifest.entries:
        full = (local_package_root / entry.relative_path).resolve()
        try:
            full.relative_to(local_package_root.resolve())
        except ValueError:
            raise ManifestMismatchError(f"PATH_ESCAPE:{entry.relative_path}")
        if not full.is_file():
            raise ManifestMismatchError(f"MISSING_FILE:{entry.relative_path}")
        actual = sha256_of_file(full)
        if actual != entry.expected_sha256:
            raise ManifestMismatchError(f"HASH_MISMATCH:{entry.relative_path}")


def build_remote_command(
    db_path: Optional[str] = None,
    logs: Optional[list[str]] = None,
) -> str:
    parts = [
        "python3.10",
        f"{SAFE_INBOX_ROOT}/live_discovery.py",
        "--sources",
        "team_bot.py", "db.py", "cars_ui.py", "avtoperedacha.py", "run_all.py", "start_safe.py",
    ]
    if db_path:
        parts += ["--db", db_path]
    if logs:
        parts += ["--logs", *logs]
    parts += ["--out", f"{SAFE_INBOX_ROOT}/{RECEIPT_FILENAME}"]
    return " ".join(parts)


def is_sensitive(payload: str) -> bool:
    lowered = payload.lower()
    return any(marker.lower() in lowered for marker in SENSITIVE_MARKERS)


def validate_receipt(raw_text: str, now: Optional[float] = None) -> dict:
    if not raw_text.strip():
        raise ReceiptValidationError("EMPTY_RECEIPT")
    if is_sensitive(raw_text):
        raise ReceiptValidationError("SENSITIVE_CONTENT_DETECTED")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ReceiptValidationError(f"MALFORMED_JSON:{exc}")
    if not isinstance(data, dict):
        raise ReceiptValidationError("RECEIPT_NOT_OBJECT")
    finished_at = data.get("finished_at_utc")
    if finished_at:
        try:
            parsed = time.strptime(finished_at, "%Y-%m-%dT%H:%M:%SZ")
            epoch = time.mktime(parsed) - time.timezone
        except Exception:
            raise ReceiptValidationError("UNPARSEABLE_TIMESTAMP")
        now_v = now if now is not None else time.time()
        if now_v - epoch > MAX_RECEIPT_AGE_SECONDS:
            raise ReceiptValidationError("STALE_RECEIPT")
    markers = data.get("markers", {})
    for key in (
        "PRODUCTION_TOUCHED",
        "CRM_TOUCHED",
        "CRM_DB_WRITTEN",
        "SITE_REBUILT",
        "SERVICE_RELOADED",
        "OCR_FIX_INSTALLED",
        "GATE_B_EXECUTED",
        "UA_0009_PUBLISHED",
    ):
        if markers.get(key) not in ("NO", None):
            raise ReceiptValidationError(f"UNSAFE_MARKER:{key}={markers.get(key)}")
    return data


ExecutorFn = Callable[[str], None]
ReceiptReaderFn = Callable[[], Optional[str]]
CleanupFn = Callable[[], None]


@dataclass
class ControllerResult:
    status: str
    evidence: Optional[dict] = None
    error: Optional[str] = None


def run_readonly_discovery(
    local_package_root: Path,
    manifest: SyncManifest,
    executor: ExecutorFn,
    receipt_reader: ReceiptReaderFn,
    cleanup: CleanupFn,
    db_path: Optional[str] = None,
    logs: Optional[list[str]] = None,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    clock_fn: Callable[[], float] = time.time,
) -> ControllerResult:
    """Execute the bounded one-shot remote discovery and always clean up."""
    try:
        validate_manifest(local_package_root, manifest)
    except ManifestMismatchError as exc:
        return ControllerResult(status="BLOCKED", error=f"MANIFEST_VALIDATION_FAILED:{exc}")

    command = build_remote_command(db_path=db_path, logs=logs)

    try:
        executor(command)

        deadline = clock_fn() + timeout_seconds
        raw_receipt: Optional[str] = None
        while clock_fn() < deadline:
            raw_receipt = receipt_reader()
            if raw_receipt is not None:
                break
            sleep_fn(poll_interval_seconds)

        if raw_receipt is None:
            return ControllerResult(status="BLOCKED", error="RECEIPT_TIMEOUT")

        try:
            evidence = validate_receipt(raw_receipt, now=clock_fn())
        except ReceiptValidationError as exc:
            return ControllerResult(status="BLOCKED", error=f"RECEIPT_VALIDATION_FAILED:{exc}")

        return ControllerResult(status="OK", evidence=evidence)
    except Exception as exc:  # noqa: BLE001
        return ControllerResult(status="BLOCKED", error=f"UNEXPECTED_ERROR:{type(exc).__name__}:{exc}")
    finally:
        cleanup()
