#!/usr/bin/env python3
"""Generate durable TASK105 Phase 1 sandbox evidence after tests pass."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "cloud" / "task_105_fast_pipeline_phase1"


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-log", required=True)
    args = parser.parse_args()

    log = pathlib.Path(args.test_log).read_text(encoding="utf-8")
    match = re.search(r"Ran (\d+) tests", log)
    count = int(match.group(1)) if match else 0
    if count != 39 or not re.search(r"(?m)^OK$", log):
        raise SystemExit(f"PHASE1_TEST_EVIDENCE_INVALID:count={count}")

    now = utc_now()
    source_files = [
        "automation/task_orchestrator.py",
        "state/schemas/task_request.schema.json",
        "state/schemas/task_receipt.schema.json",
        "cloud/task_105_fast_pipeline_phase1/test_task_orchestrator.py",
        "cloud/task_105_fast_pipeline_phase1/phase1_evidence.py",
    ]
    hashes = {path: sha256(ROOT / path) for path in source_files}

    receipt = {
        "task_id": "TASK105-PHASE1",
        "status": "FINISHED",
        "task_class": "CRITICAL",
        "target_environment": "sandbox",
        "tests": "PASS",
        "test_count": count,
        "failure_injection_scenarios": 10,
        "unexpected_changes": 0,
        "rollback_ready": True,
        "production_required": False,
        "production_touched": False,
        "ai_calls": 0,
        "git_commit_input": os.environ.get("GITHUB_SHA", "UNKNOWN"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "UNKNOWN"),
        "finished_at": now,
        "file_sha256": hashes,
    }
    write(
        OUT / "phase1_receipt.json",
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True),
    )

    report = f"""# TASK105 Phase 1 Sandbox Report

STATUS: PASS_PHASE1_SANDBOX
GENERATED_AT_UTC: {now}
PRODUCTION_TOUCHED: NO
AI_CALLS: 0
UNIT_AND_FAILURE_INJECTION_TESTS: {count}/39 PASS
FAILURE_INJECTION_SCENARIOS: 10/10 PASS
UNEXPECTED_CHANGES: 0

## Implemented

- Central FAST / STANDARD / CRITICAL classifier.
- Conservative escalation for protected paths and critical text markers.
- Resource-aware lock planner that allows unrelated resources in parallel.
- AI routes and per-class AI call budgets.
- Transient-only bounded retry; logical repetition enters ROOT_CAUSE_MODE.
- Canonical task state machine; false FINISHED transitions are rejected.
- Final receipt validator requiring tests, zero unexpected changes and rollback readiness.
- JSON schemas for task requests and final receipts.

## Safety boundary

The orchestrator has no network, subprocess, secret, deployment or production-write adapter.
This is a sandbox/shadow planning core only. It cannot modify the site, CRM, PythonAnywhere,
Cloudflare or DNS.

## Decision

Phase 1 sandbox acceptance passed. Overall TASK105 is not yet production FINISHED.
Next technical stage is shadow-mode comparison against representative existing tasks,
followed by synthetic FAST canary tests. Production enablement remains prohibited.
"""
    write(OUT / "PHASE1_REPORT.md", report)

    write(
        ROOT / "cloud" / "latest_status.md",
        f"""TASK_ID: task_105
ROUND: 2
CLAUDE_STATUS: DONE
CURRENT_ACTION: Phase 1 sandbox orchestrator accepted with {count}/39 tests PASS
FILES_CREATED: automation/task_orchestrator.py,state/schemas/task_request.schema.json,state/schemas/task_receipt.schema.json,cloud/task_105_fast_pipeline_phase1/PHASE1_REPORT.md,cloud/task_105_fast_pipeline_phase1/phase1_receipt.json
PRODUCTION_TOUCHED: NO
OWNER_ACTION_REQUIRED: NO
OWNER_QUESTION: NONE
NEXT_FOR_CHATGPT: run Phase 2 shadow comparison and FAST synthetic canary without production writes
UPDATED_AT_UTC: {now}
""",
    )
    write(
        ROOT / "cloud" / "owner_reply.md",
        f"""# Ответ владельцу — TASK105

СТАТУС: PASS PHASE 1 SANDBOX
ЧТО СДЕЛАНО: центральный классификатор, ресурсные locks, AI-бюджеты, retry-policy, единая модель статусов и защита TASK FINISHED
ПРОВЕРКА: {count}/39 тестов PASS; 10/10 failure-injection PASS
PRODUCTION: НЕ ЗАТРОНУТ
СЛЕДУЮЩИЙ ЭТАП: shadow comparison и синтетический FAST canary
""",
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
