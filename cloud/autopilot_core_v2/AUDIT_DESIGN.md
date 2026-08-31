# UA ART AUTOPILOT CORE v2.0 — AUDIT + DESIGN

## Confirmed architectural gaps
1. Existing watchdog is workflow-centric: it detects stalled/timeout-like GitHub Actions and can rerun only selected safe workflows. It does not own the business lifecycle of a task.
2. Existing TASK096 orchestrator is task-specific and advances a single task state machine. It is not a global scheduler/registry for all UA ART tasks.
3. A successful workflow conclusion can occur while business acceptance criteria remain incomplete.
4. Retry mechanisms are fragmented across workflows/controllers and do not share a durable global retry/repair budget.
5. No global queue provides one authoritative record of RUNNING / WAITING / BLOCKED / COMPLETE across tasks.
6. Heartbeat is not tied to business progress, so a green watchdog does not prove useful work is advancing.
7. Production authorization is task-local and inconsistent; CORE v2 must default to deny.

## Target architecture
Owner command -> Task Intake -> Global Queue -> Central Orchestrator -> Stage Executor -> Evidence Validator -> Business Acceptance -> Complete.

Every task has persistent state. Required states:
QUEUED, RUNNING, RETRY_WAIT, REPAIR_REQUIRED, OWNER_BLOCKED, SAFETY_STOP, VERIFYING, COMPLETE, FAILED_TERMINAL.

Each task records:
task_id, title, priority, requested_at, current_stage, business_status, percent, heartbeat_at, last_progress_at, last_error, error_class, transient_retries, repair_attempts, stage_restarts, production_authorized, rollback_available, acceptance, evidence, history.

## Error classes
TRANSIENT: 408/409-ready/412-ready/425/429/500/502/503/504, network timeout, temporary lock, runner interruption.
CODE_CONFIG: syntax/import/schema/entrypoint/configuration deterministic failures.
EXTERNAL_OWNER: password, 2FA, CAPTCHA, expired owner token, legally/operationally required explicit approval.
SAFETY: production scope violation, forbidden data write, forbidden secret/price handling, guard bypass attempt.
TERMINAL_EXTERNAL: externally unavailable dependency after bounded retries with no safe alternate path.

## Recovery policy
TRANSIENT -> exponential bounded retry, up to 10 per stage.
CODE_CONFIG -> do not blindly retry identical code; enter repair path, validate compile/tests, restart failed stage only.
EXTERNAL_OWNER -> OWNER_BLOCKED with exact one-line action required.
SAFETY -> hard stop, no bypass.
TERMINAL_EXTERNAL -> alternate safe executor/provider if declared; otherwise owner notification.

## Heartbeat policy
Heartbeat alone is insufficient. The core stores both heartbeat_at and last_progress_at. If heartbeat updates while last_progress_at exceeds the stage budget, classify STALLED_NO_PROGRESS and repair/restart.

## Completion policy
GitHub `success` = executor success only.
BUSINESS_COMPLETE requires all declared acceptance checks true plus factual postcheck evidence. No task may become COMPLETE from workflow conclusion alone.

## Locking
Global orchestrator single-instance lock.
Resource locks: production-site, live-crm, bot-runtime, pythonanywhere-console, catalog-writer. Read-only/sandbox tasks may run concurrently when resources do not conflict.

## Production gate
CORE v2 production is DENY by default. No production-changing stage runs unless the task state contains an explicit production authorization artifact. Recovery code cannot modify or synthesize that authorization.

## Rollback
Before any authorized mutable production stage: snapshot/backup ID is mandatory. On failed postcheck: rollback and re-verify. If rollback fails: SAFETY_STOP.

## Failure-injection acceptance tests
- transient 502 -> retry -> success
- PythonAnywhere 412 console-not-ready -> readiness retry without owner
- syntax/import error -> repair path, not 10 identical retries
- runner death -> resume from checkpoint
- duplicate execution -> single-instance/resource lock rejects second writer
- workflow success but acceptance false -> task remains RUNNING/VERIFYING
- stale heartbeat with no progress -> restart/repair
- production unauthorized -> hard stop
- production postcheck failure -> rollback
- owner-only 2FA -> OWNER_BLOCKED

## Definition of Done for CORE v2 sandbox
GLOBAL_QUEUE_TEST: PASS
PERSISTENT_STATE_TEST: PASS
HEARTBEAT_PROGRESS_TEST: PASS
AUTOMATIC_RESUME_TEST: PASS
ERROR_CLASSIFICATION_TEST: PASS
BOUNDED_RETRY_TEST: PASS
REPAIR_PATH_TEST: PASS
SINGLE_INSTANCE_LOCK_TEST: PASS
RESOURCE_LOCK_TEST: PASS
PRODUCTION_DENY_DEFAULT_TEST: PASS
BUSINESS_COMPLETE_GATE_TEST: PASS
ROLLBACK_STATE_TEST: PASS
OWNER_BLOCKER_TEST: PASS

Production installation is explicitly out of scope until separate owner approval.