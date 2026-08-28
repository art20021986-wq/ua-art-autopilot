#!/usr/bin/env python3
"""
TASK_058 task058_readonly_controller.py

Read-only controller for CRM-OCR-SYNC-001 Round 1 discovery. Mirrors the
safety pattern of cloud/bot_logistics/pythonanywhere_discovery_controller.py
without modifying that file. This controller never performs writes to
production, CRM, the database, or any service. It:

  1. validates a local manifest (path + expected SHA-256) before any sync;
  2. syncs exactly the manifest files into the safe inbox (via injected
     transport, so this module has zero real network code and is fully
     unit-testable offline);
  3. builds one exact, allowlist-checked remote command and executes it via
     injected transport;
  4. polls for exactly one receipt with a bounded timeout;
  5. validates the receipt (size bound, sensitive-token rejection, malformed
     or stale rejection);
  6. relays sanitized evidence to a local report file;
  7. deletes the remote trigger and receipt in `finally`, on success,
     failure, or timeout.

All remote transport is dependency-injected (`sync_fn`, `run_fn`, `poll_fn`,
`cleanup_fn`). No real SSH/SCP call exists in this module; production use
requires binding those functions to a tightly-scoped transport limited to the
safe inbox directory, which is outside the scope of this offline-testable
Round 1 deliverable.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

SAFE_INBOX_DIR = "/home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync"
RECEIPT_NAME = "task_058_live_discovery_receipt.json"
TRIGGER_NAME = "task_058_trigger.flag"
SCRIPT_NAME = "live_discovery.py"
PYTHON_BIN = "python3.10"
MAX_RECEIPT_AGE_SECONDS = 900
MAX_RECEIPT_BYTES = 2_000_000

SENSITIVE_TOKENS = ("token", "api_key", "apikey", "password", "secret", "authorization")

FORBIDDEN_COMMAND_TOKENS = ("sudo", "*", "find ", ">", ">>", "&&", "|", ";", "rm ", "reload")


class ControllerError(Exception):
    pass


@dataclass
class ControllerConfig:
    manifest: List[dict]
    allowlist_file_remote: str
    receipt_local_path: str
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 60.0


class ReadOnlyController:
    """
    Dependency-injected controller. In production use, `sync_fn`, `run_fn`,
    `poll_fn`, and `cleanup_fn` must be bound to real, tightly-scoped SSH/SCP
    calls limited to the safe inbox directory. Tests inject fakes so the
    safety logic (manifest validation, command construction, receipt
    validation, guaranteed cleanup) is fully verifiable offline.
    """

    def __init__(
        self,
        config: ControllerConfig,
        sync_fn: Callable[[list], None],
        run_fn: Callable[[str], None],
        poll_fn: Callable[[], Optional[str]],
        cleanup_fn: Callable[[], None],
    ):
        self.config = config
        self.sync_fn = sync_fn
        self.run_fn = run_fn
        self.poll_fn = poll_fn
        self.cleanup_fn = cleanup_fn
        self.result = {
            "PRODUCTION_TOUCHED": "NO",
            "CRM_TOUCHED": "NO",
            "CRM_DB_WRITTEN": "NO",
            "SITE_REBUILT": "NO",
            "SERVICE_RELOADED": "NO",
            "OCR_FIX_INSTALLED": "NO",
            "GATE_B_EXECUTED": "NO",
            "UA_0009_PUBLISHED": "NO",
        }

    def validate_manifest(self) -> None:
        for entry in self.config.manifest:
            p = Path(entry["local_path"])
            if not p.exists() or p.is_symlink() or not p.is_file():
                raise ControllerError(f"MANIFEST_PATH_INVALID:{entry['local_path']}")
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if h != entry["expected_sha256"]:
                raise ControllerError(
                    f"MANIFEST_HASH_MISMATCH:{entry['local_path']}:{h}"
                )

    def build_remote_command(self) -> str:
        receipt_remote = f"{SAFE_INBOX_DIR}/{RECEIPT_NAME}"
        script_remote = f"{SAFE_INBOX_DIR}/{SCRIPT_NAME}"
        allowlist_remote = self.config.allowlist_file_remote
        cmd = (
            f"{PYTHON_BIN} {script_remote} "
            f"--allowlist-file {allowlist_remote} "
            f"--output {receipt_remote} "
            f"--receipt-base-dir {SAFE_INBOX_DIR}"
        )
        for tok in FORBIDDEN_COMMAND_TOKENS:
            if tok in cmd:
                raise ControllerError(f"UNSAFE_COMMAND_TOKEN:{tok}")
        return cmd

    def validate_receipt(self, raw: str) -> dict:
        if len(raw.encode("utf-8")) > MAX_RECEIPT_BYTES:
            raise ControllerError("RECEIPT_TOO_LARGE")
        lowered = raw.lower()
        for tok in SENSITIVE_TOKENS:
            if tok in lowered:
                raise ControllerError(f"RECEIPT_SENSITIVE_CONTENT:{tok}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ControllerError(f"RECEIPT_MALFORMED:{exc}")
        if not isinstance(data, dict) or "generated_at" not in data:
            raise ControllerError("RECEIPT_MISSING_TIMESTAMP")
        try:
            age = time.time() - float(data["generated_at"])
        except (TypeError, ValueError):
            raise ControllerError("RECEIPT_BAD_TIMESTAMP")
        if age > MAX_RECEIPT_AGE_SECONDS or age < -30:
            raise ControllerError(f"RECEIPT_STALE_OR_FUTURE:{age}")
        return data

    def run(self) -> dict:
        started = time.time()
        try:
            self.validate_manifest()
            self.sync_fn(self.config.manifest)
            cmd = self.build_remote_command()
            self.run_fn(cmd)

            raw = None
            deadline = started + self.config.poll_timeout_seconds
            while time.time() < deadline:
                raw = self.poll_fn()
                if raw is not None:
                    break
                time.sleep(self.config.poll_interval_seconds)
            if raw is None:
                raise ControllerError("RECEIPT_POLL_TIMEOUT")

            evidence = self.validate_receipt(raw)
            Path(self.config.receipt_local_path).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self.result["status"] = "READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058"
            self.result["evidence_relayed"] = True
            return dict(self.result)
        except ControllerError as exc:
            self.result["status"] = f"BLOCKED_WITH_EXACT_REASON_TASK_058:{exc}"
            self.result["evidence_relayed"] = False
            return dict(self.result)
        finally:
            try:
                self.cleanup_fn()
            except Exception:
                pass
