#!/usr/bin/env python3
"""TASK104 sandbox acceptance suite. No production/live writes."""
from __future__ import annotations

import json
import pathlib
import sys

import task104_self_recovery_core as core


def run_failure_tests() -> dict[str, bool]:
    tests: dict[str, bool] = {}
    transient = [
        "PYTHONANYWHERE_HTTP_408", "PYTHONANYWHERE_HTTP_409", "PYTHONANYWHERE_HTTP_412",
        "PYTHONANYWHERE_HTTP_425", "PYTHONANYWHERE_HTTP_429", "PYTHONANYWHERE_HTTP_500",
        "PYTHONANYWHERE_HTTP_502", "PYTHONANYWHERE_HTTP_503", "PYTHONANYWHERE_HTTP_504",
        "TimeoutError", "NetworkError", "Connection reset", "database is locked",
        "RUNNER_LOST", "WORKFLOW_CANCELLED", "REMOTE_RECEIPT_TIMEOUT",
    ]
    tests["TRANSIENT_CLASSIFICATION"] = all(core.classify_error(x) == "TRANSIENT" for x in transient)
    tests["CODE_CONFIG_CLASSIFICATION"] = all(core.classify_error(x) == "CODE_CONFIG" for x in ("SyntaxError", "AttributeError", "ImportError", "SCHEMA_MISMATCH"))
    tests["SAFETY_CLASSIFICATION"] = core.classify_error("REMOTE_SCOPE_VIOLATION:bot_code_changed") == "SAFETY"
    tests["OWNER_ONLY_CLASSIFICATION"] = core.classify_error("2FA required") == "OWNER_ONLY"

    bounded = core.new_task("BOUNDED")
    bounded["current_stage"] = "SANDBOX"
    for _ in range(core.MAX_RECOVERY):
        core.plan_recovery(bounded, "HTTP_502")
    tests["TEN_RECOVERIES_ALLOWED"] = bounded["business_status"] == "RETRY_WAIT" and core.recovery_count(bounded, "SANDBOX") == 10
    core.plan_recovery(bounded, "HTTP_502")
    tests["ELEVENTH_RECOVERY_STOPS"] = bounded["business_status"] == "TERMINAL_EXTERNAL"

    safety = core.new_task("SAFETY")
    safety["current_stage"] = "POSTCHECK"
    safety["production_started"] = True
    safety["rollback_available"] = True
    action = core.plan_recovery(safety, "REMOTE_SCOPE_VIOLATION:bot_code_changed")
    tests["SAFETY_ROLLBACK"] = action == "STOP_SAFETY" and safety["rollback_performed"] is True and safety["business_status"] == "SAFETY_STOP"

    owner = core.new_task("OWNER")
    action = core.plan_recovery(owner, "2FA required")
    tests["OWNER_ONLY_STOP"] = action == "ASK_OWNER" and owner["business_status"] == "OWNER_BLOCKED" and owner["owner_input_count"] == 1

    lost = core.new_task("LOST-EVENT")
    core.stage_start(lost, "BACKUP")
    core.stage_pass(lost, "BACKUP")
    lost["executor"] = None
    lost["lease_until"] = 0
    lost["last_progress_at"] = 100
    tests["LOST_EVENT_RECONCILIATION"] = core.reconciliation_sweep(lost, False, at=1000) == "RESUMED" and lost["current_stage"] == "INTAKE"

    # A realistic task would checkpoint INTAKE before BACKUP. Verify resume skips all proven stages.
    resume = core.new_task("RESUME")
    for stage in ("INTAKE", "BACKUP", "SANDBOX"):
        core.stage_start(resume, stage)
        core.stage_pass(resume, stage)
    resume["executor"] = None
    resume["lease_until"] = 0
    resume["last_progress_at"] = 100
    core.reconciliation_sweep(resume, False, at=1000)
    tests["CHECKPOINT_RESUME"] = resume["current_stage"] == "CANARY" and resume["completed_stages"] == ["INTAKE", "BACKUP", "SANDBOX"]

    lock = core.new_task("LOCK")
    lock["locks"]["production-site"] = {"owner": "OTHER", "lease_until": 2000}
    tests["ACTIVE_LOCK_BLOCKS_DUPLICATE"] = core.acquire_lock(lock, "production-site", 3000, 1000) is False
    lock["locks"]["production-site"] = {"owner": "DEAD", "lease_until": 100}
    tests["STALE_LOCK_RECOVERY"] = core.acquire_lock(lock, "production-site", 3000, 1000) is True

    incomplete = core.new_task("INCOMPLETE")
    incomplete["acceptance"] = {"browser": False}
    incomplete["evidence"] = {"workflow": "success"}
    tests["WORKFLOW_SUCCESS_NOT_BUSINESS_COMPLETE"] = core.finalize(incomplete) is False and incomplete["business_status"] == "VERIFYING"

    complete = core.new_task("COMPLETE")
    complete["acceptance"] = {"browser": True, "crm": True, "site": True}
    complete["evidence"] = {"browser": "PASS", "crm": "PASS", "site": "PASS"}
    tests["BUSINESS_COMPLETE_GATE"] = core.finalize(complete) is True and complete["business_status"] == "BUSINESS_COMPLETE"

    progress = core.new_task("PROGRESS")
    progress["business_status"] = "RUNNING"
    progress["executor"] = "alive"
    progress["lease_until"] = 2000
    progress["heartbeat_at"] = 999
    progress["last_progress_at"] = 100
    tests["HEARTBEAT_WITHOUT_PROGRESS_RECOVERS"] = core.reconciliation_sweep(progress, True, at=1000, progress_budget=300) == "RESUMED"

    return tests


def run_canaries() -> list[dict]:
    scenarios = [
        ("SANDBOX", "TimeoutError"),
        ("SANDBOX", "PYTHONANYWHERE_HTTP_412"),
        ("CANARY", "PYTHONANYWHERE_HTTP_429"),
        ("CANARY", "PYTHONANYWHERE_HTTP_502"),
        ("EXECUTE", "Connection reset"),
        ("EXECUTE", "RUNNER_LOST"),
        ("POSTCHECK", "WORKFLOW_CANCELLED"),
        ("POSTCHECK", "LOST_WORKFLOW_EVENT"),
        ("SANDBOX", "database is locked"),
        ("CANARY", "AttributeError in executor"),
    ]
    return [core.run_one_canary(i, stage, failure) for i, (stage, failure) in enumerate(scenarios, start=1)]


def main() -> int:
    core.require_approval()
    tests = run_failure_tests()
    canaries = run_canaries()
    failed_tests = sorted(name for name, passed in tests.items() if not passed)
    failed_canaries = [item for item in canaries if item.get("status") != "PASS" or item.get("business_status") != "BUSINESS_COMPLETE" or item.get("owner_input_count") != 0]
    report = {
        "contract": core.CONTRACT,
        "status": "PASS" if not failed_tests and not failed_canaries else "FAIL",
        "phase": "AUDIT_DESIGN_SANDBOX_FAILURE_INJECTION_10X_CANARY_REPORT",
        "failure_injection": {"tests": tests, "failed": failed_tests, "passed": len(tests) - len(failed_tests), "total": len(tests)},
        "autonomous_canary": {"passed": len(canaries) - len(failed_canaries), "total": len(canaries), "required": "10/10", "cycles": canaries},
        "production_recovery_core_authorized": False,
        "production_touched": False,
        "live_crm_write": False,
        "site_write": False,
        "bot_write": False,
        "card_write": False,
        "media_write": False,
        "task096_v8_touched": False,
        "owner_manual_push_required": False if not failed_canaries else True,
        "ready_for_production_review": not failed_tests and not failed_canaries,
    }
    core.atomic_json(core.REPORT, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
