# TASK 078 — CRM-VOICE-WATCHDOG-005 v1.0

## Scope
Build an automatic-restart watchdog for the CRM voice/audio transcription path
so a hung `ai.transcribe` call inside `cars_ui.py::catch_message` can no
longer leave orphan workers or freeze the bot. This package is delivered as
GET-only audit design + sandbox implementation + tests + installer/rollback.
No production write, no CRM write, no live restart was performed by this
worker.

## Governing constraint
OWNER_DIRECTIVE (task_078): `GET-only AUDIT → SANDBOX/CANARY → release
candidate`. Production is forbidden until a separate written owner command.
TASK 077 is not touched or stopped.

## What is inside this folder
- `gate_a_audit.md` — Gate A read-only audit status and required evidence.
- `killable_stt_worker.py` — spawn-based killable STT worker (TERM→wait→KILL).
- `job_marker.py` — bounded job-marker store (no text/audio/PII).
- `circuit_breaker.py` — 3-timeouts/10min → 5min cooldown breaker.
- `handler_patch.py` — design + reference implementation of the patched
  `catch_message` voice branch, built against the contract in task_078.
- `installer.py` — backup/apply/rollback installer, Gate B manual, not run.
- `controller.py` — supervisor-detection + restart-budget/cooldown logic for
  the (only conditionally allowed) full-process restart path.
- `tests/test_watchdog.py` — offline sandbox test suite covering every
  scenario listed in task_078 "Sandbox tests".
- `sandbox_report.md` — status of test design/execution and what remains for
  independent controller execution.

## Verdict
See `sandbox_report.md` and `cloud/latest_status.md`.
Final contractual verdict for this round: **FAIL — GATE_A_NOT_EXECUTED**
(package is `READY_FOR_CONTROLLER_GATE_A_EXECUTION`; it is not
`PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` yet because this worker has no
live secret-backed GET access to fetch and hash the actual production
`cars_ui.py`, `ai.py`, `start_safe.py`, `crm_online_guard.py`, and the real
launcher/supervisor manifest).

## AUTOPILOT VERIFIED CANONICAL SHARED MEMORY
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
CURRENT_STATUS.ua0009_safe_to_publish: NO
