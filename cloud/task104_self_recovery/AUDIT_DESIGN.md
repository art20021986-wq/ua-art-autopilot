# TASK104 — Self-Recovery Audit & Design

Contract: `UA-AUTOPILOT-SELF-RECOVERY-104-V1.0`
Mode: SANDBOX ONLY
Production Recovery Core: NOT AUTHORIZED

## Audit findings

1. TASK096 v7 failed on a PythonAnywhere network read timeout before its transport fallback could take control. A network exception was raised by the shared request layer, so the v7 launcher never reached its HTTP-status fallback branch.
2. TASK096 v8 improved request retries but still remained a task-local wrapper rather than a repository-wide recovery supervisor.
3. The existing Safe Workflow Watchdog is useful for hangs but is not a business-task supervisor. Its explicit subscriptions do not cover TASK096 v7/v8 and its generic safe-name rule is not a reliable registry of approved tasks.
4. TASK096 Recovery10 contains bounded recovery behavior but has no `workflow_run` trigger from the current enrichment workflow, so it cannot guarantee automatic continuation after a failed run.
5. Autopilot Core v2 already has the correct conceptual primitives: persistent state, error classification, bounded transient retries, owner-only classification and BUSINESS_COMPLETE gating. It is not yet wired as the mandatory execution/reconciliation layer for real tasks.
6. A second real-world failure was observed on TASK096 v8 before TASK104 execution began: the context export completed, then its safety validator stopped on `REMOTE_SCOPE_VIOLATION:bot_code_changed`. This is correctly a SAFETY-class stop, not a transient retry. TASK104 must preserve this distinction and must never blindly retry safety violations.

## Root cause

Recovery is fragmented across workflow-local retry code, a hang watchdog, task-specific recovery jobs and a sandbox core. There is no single authoritative task ledger plus event-driven recovery plus independent reconciliation sweep. Therefore a workflow can fail while the business task has no active executor and no component owns continuation.

## Target architecture

`Task Ledger -> Event Receiver -> Error Classifier -> Recovery Planner -> Executor -> Checkpoint Store -> Acceptance Verifier -> BUSINESS_COMPLETE`

In parallel:

`Reconciliation Sweep -> find non-terminal task with no valid executor/lease -> resume from last proven checkpoint`

### Required state per task

- task_id / contract / priority
- current_stage / last_checkpoint
- business_status / percent
- heartbeat_at / last_progress_at
- executor lease / resource locks
- stage attempt count / recovery count
- error class / last error / recovery action
- production permission
- rollback availability
- acceptance map / evidence map
- immutable history

### Error classes

- `TRANSIENT`: HTTP 408/409/412/425/429/5xx, timeout, network reset, database locked, runner lost. Bounded retry/fallback, max 10 per stage.
- `CODE_CONFIG`: SyntaxError, AttributeError, ImportError, schema/config mismatch. Enter repair path; compile/tests before restarting only the failed stage.
- `SAFETY`: forbidden write, scope violation, guard bypass, unexpected protected change. Stop immediately; rollback if a production write began. Never blind retry.
- `OWNER_ONLY`: 2FA, CAPTCHA, missing owner credential/permission that cannot be safely derived. Ask owner exactly once with the required action.
- `TERMINAL_EXTERNAL`: dependency remains unavailable after bounded alternatives/retries.

## Transport rule

Transport fallback is exception-aware, not only HTTP-status-aware:

`primary -> scheduled one-shot -> alternate safe launcher -> bounded retry/backoff`

A Timeout/NetworkError must advance the fallback plan instead of terminating the task.

## Checkpoint rule

Every successful stage writes an atomic checkpoint. Recovery resumes from the last proven checkpoint. Completed backup/canary/data batches are not repeated unless their evidence is invalidated.

## Heartbeat rule

`heartbeat_at` proves the executor is alive. `last_progress_at` proves the business stage advanced. A live heartbeat without progress beyond the stage budget is a stall and enters recovery.

## Completion rule

GitHub `success` is never sufficient. `BUSINESS_COMPLETE` requires all task-specific acceptance checks plus evidence. Production tasks additionally require backup, sandbox, canary, safety, production write, postchecks and browser/CRM/site acceptance.

## TASK104 sandbox acceptance

- Required failure scenarios pass.
- Lost-event reconciliation resumes work.
- Stale lock is recovered safely; active lock blocks duplicate dispatch.
- Checkpoint resume does not replay completed stages.
- Safety and owner-only cases stop safely instead of blind retry.
- 10/10 autonomous canary cycles reach BUSINESS_COMPLETE without owner input.
- No production/live CRM/site/bot/card/media write.

Only after a separate owner approval may the Recovery Core be connected to production execution.
