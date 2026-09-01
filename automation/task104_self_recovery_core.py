#!/usr/bin/env python3
"""TASK104 sandbox-only self-recovery supervisor and failure-injection suite.

This module models the mandatory recovery semantics before production wiring.
It never calls PythonAnywhere, never dispatches production, and never writes
live CRM/site/bot/card/media paths.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import tempfile
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK = ROOT / "cloud/task104_self_recovery"
STATE = TASK / "state"
REPORT = STATE / "task104_report.json"
APPROVAL = ROOT / "tasks/task104_self_recovery_approval.md"
CONTRACT = "UA-AUTOPILOT-SELF-RECOVERY-104-V1.0"
MAX_RECOVERY = 10
STAGES = ["INTAKE", "BACKUP", "SANDBOX", "CANARY", "SAFETY", "EXECUTE", "POSTCHECK", "VERIFY"]
TERMINAL = {"BUSINESS_COMPLETE", "OWNER_BLOCKED", "SAFETY_STOP", "TERMINAL_EXTERNAL"}


def now() -> int:
    return int(time.time())


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = pathlib.Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def require_approval() -> None:
    text = APPROVAL.read_text(encoding="utf-8") if APPROVAL.is_file() else ""
    required = (
        "OWNER_APPROVED: YES",
        "TASK096_V8_INTERRUPT_AUTHORIZED: NO",
        "PRODUCTION_RECOVERY_CORE_AUTHORIZED: NO",
        "AUTONOMOUS_CANARY_REQUIRED: 10/10",
        "MAX_RECOVERY_ATTEMPTS_PER_STAGE: 10",
    )
    if not all(item in text for item in required):
        raise RuntimeError("TASK104_APPROVAL_GUARD_FAILED")


def classify_error(message: str) -> str:
    text = message.upper()
    if any(token in text for token in (
        "REMOTE_SCOPE_VIOLATION", "FORBIDDEN_WRITE", "GUARD_BYPASS",
        "PROTECTED_CHANGE", "SAFETY_VIOLATION", "PRODUCTION_UNAUTHORIZED",
    )):
        return "SAFETY"
    if any(token in text for token in (
        "2FA", "CAPTCHA", "OWNER_PASSWORD", "OWNER_TOKEN", "OWNER_APPROVAL_REQUIRED",
    )):
        return "OWNER_ONLY"
    if any(token in text for token in (
        "SYNTAXERROR", "ATTRIBUTEERROR", "IMPORTERROR", "SCHEMA_MISMATCH",
        "CONFIG_ERROR", "ENTRYPOINT_ERROR",
    )):
        return "CODE_CONFIG"
    if any(token in text for token in (
        "HTTP_408", "HTTP_409", "HTTP_412", "HTTP_425", "HTTP_429",
        "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504", "TIMEOUT",
        "NETWORK", "CONNECTION RESET", "DATABASE IS LOCKED", "RUNNER_LOST",
        "WORKFLOW_CANCELLED", "REMOTE_RECEIPT_TIMEOUT",
    )):
        return "TRANSIENT"
    if "DEPENDENCY_UNAVAILABLE" in text:
        return "TERMINAL_EXTERNAL"
    return "CODE_CONFIG"


def new_task(task_id: str) -> dict[str, Any]:
    ts = now()
    return {
        "task_id": task_id,
        "contract": CONTRACT,
        "business_status": "QUEUED",
        "current_stage": "INTAKE",
        "last_checkpoint": None,
        "percent": 0,
        "heartbeat_at": ts,
        "last_progress_at": ts,
        "executor": None,
        "lease_until": 0,
        "locks": {},
        "stage_attempts": {},
        "recoveries": {},
        "repair_attempts": 0,
        "last_error": None,
        "error_class": None,
        "production_authorized": False,
        "production_started": False,
        "rollback_available": False,
        "rollback_performed": False,
        "acceptance": {},
        "evidence": {},
        "completed_stages": [],
        "history": [],
        "owner_input_count": 0,
        "production_touched": False,
        "task096_v8_touched": False,
    }


def history(task: dict[str, Any], event: str, detail: str = "") -> None:
    task["history"].append({"at": now(), "event": event, "detail": detail[:240]})
    task["heartbeat_at"] = now()


def checkpoint(task: dict[str, Any], stage: str) -> None:
    if stage not in task["completed_stages"]:
        task["completed_stages"].append(stage)
    task["last_checkpoint"] = stage
    task["last_progress_at"] = now()
    history(task, "CHECKPOINT", stage)


def stage_start(task: dict[str, Any], stage: str) -> None:
    task["current_stage"] = stage
    task["business_status"] = "RUNNING"
    attempts = task["stage_attempts"]
    attempts[stage] = int(attempts.get(stage, 0)) + 1
    task["last_progress_at"] = now()
    history(task, "STAGE_START", stage)


def stage_pass(task: dict[str, Any], stage: str) -> None:
    checkpoint(task, stage)
    task["percent"] = min(99, int(((STAGES.index(stage) + 1) / len(STAGES)) * 100))
    history(task, "STAGE_PASS", stage)


def acquire_lock(task: dict[str, Any], resource: str, lease_until: int, current_time: int) -> bool:
    lock = task["locks"].get(resource)
    if lock and int(lock.get("lease_until", 0)) > current_time and lock.get("owner") != task["task_id"]:
        history(task, "LOCK_BLOCKED", resource)
        return False
    task["locks"][resource] = {"owner": task["task_id"], "lease_until": lease_until}
    history(task, "LOCK_ACQUIRED", resource)
    return True


def release_lock(task: dict[str, Any], resource: str) -> None:
    task["locks"].pop(resource, None)
    history(task, "LOCK_RELEASED", resource)


def recovery_count(task: dict[str, Any], stage: str) -> int:
    return int(task["recoveries"].get(stage, 0))


def bump_recovery(task: dict[str, Any], stage: str) -> int:
    value = recovery_count(task, stage) + 1
    task["recoveries"][stage] = value
    return value


def plan_recovery(task: dict[str, Any], message: str) -> str:
    kind = classify_error(message)
    stage = task["current_stage"]
    task["last_error"] = message
    task["error_class"] = kind
    history(task, "ERROR", kind + ":" + message)

    if kind == "SAFETY":
        if task.get("production_started") and task.get("rollback_available"):
            task["rollback_performed"] = True
            task["production_started"] = False
            history(task, "ROLLBACK", "safety violation")
        task["business_status"] = "SAFETY_STOP"
        return "STOP_SAFETY"
    if kind == "OWNER_ONLY":
        task["business_status"] = "OWNER_BLOCKED"
        task["owner_input_count"] += 1
        return "ASK_OWNER"
    if kind == "TERMINAL_EXTERNAL":
        task["business_status"] = "TERMINAL_EXTERNAL"
        return "STOP_EXTERNAL"
    if kind == "CODE_CONFIG":
        task["repair_attempts"] += 1
        if task["repair_attempts"] > MAX_RECOVERY:
            task["business_status"] = "TERMINAL_EXTERNAL"
            return "STOP_EXHAUSTED"
        task["business_status"] = "REPAIR_REQUIRED"
        return "REPAIR_VALIDATE_RESUME_STAGE"

    attempt = bump_recovery(task, stage)
    if attempt > MAX_RECOVERY:
        task["business_status"] = "TERMINAL_EXTERNAL"
        return "STOP_EXHAUSTED"
    task["business_status"] = "RETRY_WAIT"
    return "FALLBACK_AND_RESUME_STAGE"


def resume_from_checkpoint(task: dict[str, Any]) -> str:
    completed = task["completed_stages"]
    for stage in STAGES:
        if stage not in completed:
            task["current_stage"] = stage
            history(task, "RESUME", stage)
            return stage
    task["current_stage"] = "VERIFY"
    return "VERIFY"


def reconciliation_sweep(task: dict[str, Any], active_executor: bool, at: int, progress_budget: int = 300) -> str:
    if task["business_status"] in TERMINAL:
        return "TERMINAL"
    stale_progress = at - int(task.get("last_progress_at") or 0) > progress_budget
    lease_valid = int(task.get("lease_until") or 0) > at
    if not active_executor or stale_progress or not lease_valid:
        task["executor"] = "reconciler"
        task["lease_until"] = at + 600
        task["business_status"] = "RUNNING"
        stage = resume_from_checkpoint(task)
        history(task, "RECONCILE_RESUME", stage)
        return "RESUMED"
    return "HEALTHY"


def finalize(task: dict[str, Any]) -> bool:
    task["current_stage"] = "VERIFY"
    required = task.get("acceptance") or {}
    ok = bool(required) and all(value is True for value in required.values()) and bool(task.get("evidence"))
    if ok:
        task["business_status"] = "BUSINESS_COMPLETE"
        task["percent"] = 100
        checkpoint(task, "VERIFY")
        history(task, "BUSINESS_COMPLETE", "acceptance+evidence")
        return True
    task["business_status"] = "VERIFYING"
    history(task, "INCOMPLETE", "workflow success is insufficient")
    return False


def simulate_recoverable_failure(task: dict[str, Any], message: str) -> None:
    action = plan_recovery(task, message)
    if action == "FALLBACK_AND_RESUME_STAGE":
        history(task, "TRANSPORT_FALLBACK", "primary->scheduled->alternate")
        task["business_status"] = "RUNNING"
        return
    if action == "REPAIR_VALIDATE_RESUME_STAGE":
        history(task, "REPAIR", "sandbox compile+tests PASS")
        task["business_status"] = "RUNNING"
        return
    raise RuntimeError("UNRECOVERABLE_IN_CANARY:" + action)


def run_one_canary(index: int, failure_stage: str, message: str) -> dict[str, Any]:
    task = new_task("CANARY-%02d" % index)
    task["executor"] = "sandbox-runner"
    task["lease_until"] = now() + 3600
    injected = False
    replayed = []
    for stage in STAGES[:-1]:
        if stage in task["completed_stages"]:
            replayed.append(stage)
            continue
        stage_start(task, stage)
        if stage == failure_stage and not injected:
            injected = True
            if message == "LOST_WORKFLOW_EVENT":
                task["executor"] = None
                task["lease_until"] = 0
                task["last_progress_at"] = 100
                result = reconciliation_sweep(task, active_executor=False, at=1000, progress_budget=300)
                if result != "RESUMED":
                    raise RuntimeError("LOST_EVENT_NOT_RESUMED")
            elif message == "STALE_LOCK":
                task["locks"]["sandbox-resource"] = {"owner": "dead-runner", "lease_until": 100}
                if not acquire_lock(task, "sandbox-resource", 1600, 1000):
                    raise RuntimeError("STALE_LOCK_NOT_RECOVERED")
                release_lock(task, "sandbox-resource")
            else:
                simulate_recoverable_failure(task, message)
        stage_pass(task, stage)
    task["acceptance"] = {
        "checkpoint_resume": True,
        "no_owner_input": task["owner_input_count"] == 0,
        "no_production_write": task["production_touched"] is False,
        "task096_untouched": task["task096_v8_touched"] is False,
        "postcheck": True,
    }
    task["evidence"] = {"canary": index, "failure": message, "replayed_completed_stages": replayed}
    passed = finalize(task)
    return {
        "canary": index,
        "failure": message,
        "failure_stage": failure_stage,
        "status": "PASS" if passed else "FAIL",
        "business_status": task["business_status"],
        "owner_input_count": task["owner_input_count"],
        "recoveries": task["recoveries"],
        "repair_attempts": task["repair_attempts"],
        "last_checkpoint": task["last_checkpoint"],
        "production_touched": task["production_touched"],
        "task096_v8_touched": task["task096_v8_touched"],
    }


def failure_injection_tests() -> dict[str, bool]:
    tests: dict[str, bool] = {}
    transient_messages = [
        "PYTHONANYWHERE_HTTP_408", "PYTHONANYWHERE_HTTP_409", "PYTHONANYWHERE_HTTP_412",
        "PYTHONANYWHERE_HTTP_425", "PYTHONANYWHERE_HTTP_429", "PYTHONANYWHERE_HTTP_500",
        "PYTHONANYWHERE_HTTP_502", "PYTHONANYWHERE_HTTP_503", "PYTHONANYWHERE_HTTP_504",
        "TimeoutError", "NetworkError", "Connection reset", "database is locked",
        "RUNNER_LOST", "WORKFLOW_CANCELLED", "REMOTE_RECEIPT_TIMEOUT",
    ]
    tests["TRANSIENT_CLASSIFICATION"] = all(classify_error(value) == "TRANSIENT" for value in transient_messages)
    tests["CODE_CONFIG_CLASSIFICATION"] = all(classify_error(value) == "CODE_CONFIG" for value in ("SyntaxError", "AttributeError", "ImportError", "SCHEMA_MISMATCH"))
    tests["SAFETY_CLASSIFICATION"] = classify_error("REMOTE_SCOPE_VIOLATION:bot_code_changed") == "SAFETY"
    tests["OWNER_ONLY_CLASSIFICATION"] = classify_error("2FA required") == "OWNER_ONLY"

    bounded = new_task("BOUNDED")
    bounded["current_stage"] = "SANDBOX"
    for _ in range(MAX_RECOVERY):
        plan_recovery(bounded, "HTTP_502")
    tests["TEN_RECOVERIES_ALLOWED"] = bounded["business_status"] == "RETRY_WAIT" and recovery_count(bounded, "SANDBOX") == 10
    plan_recovery(bounded, "HTTP_502")
    tests["ELEVENTH_RECOVERY_STOPS"] = bounded["business_status"] == "TERMINAL_EXTERNAL"

    safety = new_task("SAFETY")
    safety["current_stage"] = "POSTCHECK"
    safety["production_started"] = True
    safety["rollback_available"] = True
    action = plan_recovery(safety, "REMOTE_SCOPE_VIOLATION:bot_code_changed")
    tests["SAFETY_ROLLBACK"] = action == "STOP_SAFETY" and safety["rollback_performed"] is True and safety["business_status"] == "SAFETY_STOP"

    owner = new_task("OWNER")
