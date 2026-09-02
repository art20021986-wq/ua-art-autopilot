# MIGRATION_PLAN.md — TASK 105 Phase 0

## Principle
Migration must be reversible and staged. No existing workflow is deleted, disabled, or modified in Phase 0 or in the first stages of Phase 1. Everything new is additive and sandboxed until explicitly promoted.

## Stage 0 (this task — COMPLETE)
- Read-only audit, classification proposal, target architecture proposal, risk register, acceptance test plan. No files under `.github/workflows/` touched. No secrets touched. No production/CRM/PythonAnywhere/Cloudflare/DNS writes.

## Stage 1 — Shadow orchestrator (sandbox only, next phase, requires separate owner review of this Phase 0 report first)
- Build `orchestrator-classify.yml` and the resource-lock composite action in a **non-triggering** mode: it runs alongside existing workflows, logs what it *would* classify/lock, but takes no gating action and cannot block or replace any existing workflow.
- All new code lives under a clearly separated path (e.g. `automation/orchestrator/` or `cloud/orchestrator_sandbox/`) so it cannot be confused with production automation.
- Existing workflows continue to run exactly as before; nothing is archived or merged yet.

## Stage 2 — Shadow verification against real tasks
- Run several real (past or new low-risk FAST) tasks through the shadow orchestrator in parallel with the existing pipeline.
- Compare shadow classification/lock decisions against actual outcomes; tune classifier rules.
- No production-write workflow is touched at this stage.

## Stage 3 — Opt-in cutover for FAST lane only
- For a small, explicitly owner-approved subset of task types, allow the new `worker-fast.yml` to actually run (still NO production-write capability), while STANDARD/CRITICAL continue through the legacy path unchanged.
- Rollback: disabling the opt-in flag returns 100% of traffic to the legacy path with zero data loss, since FAST-lane tasks never touch production.

## Stage 4 — STANDARD lane parameterized pipeline
- Consolidate the identified duplicate/task-specific workflows (see WORKFLOW_INVENTORY.md MERGE/ARCHIVE candidates) into `worker-standard.yml`, one task type at a time, with the legacy workflow kept in ARCHIVE (not deleted) as an immediate rollback path.
- Each consolidation step requires: (a) a passing acceptance test from ACCEPTANCE_TEST_PLAN.md, (b) controller verification, (c) explicit note in `cloud/latest_status.md` that the legacy workflow remains available and unarchived until N successful runs of the new pipeline.

## Stage 5 — CRITICAL lane gate and resource-aware locking for production-apply
- Only after Stages 1–4 are stable: introduce `critical-gate.yml` and `production-apply.yml` in **shadow/dry-run mode** (computes what it would do, does not apply), reviewed by owner, before any live cutover.
- Actual production-write cutover for `production-apply.yml` requires a separate, explicit owner-approved task (this Phase 0/Migration Plan does NOT grant that approval).

## Rollback guarantees at every stage
- Every stage keeps the legacy `automation/production_queue.py` and existing workflows fully intact and runnable.
- No stage requires a one-way schema change to existing status files; new fields (e.g. `TASK_STATE`) are additive, and legacy `CLAUDE_STATUS` values continue to be honored during the transition.
- A single flag/config toggle can revert any stage's opt-in behavior without code deletion.

## Explicit non-goals of this migration plan
- Does not authorize deleting or disabling any current workflow.
- Does not authorize changing secrets or Cloudflare/DNS configuration.
- Does not authorize merging this or any related branch to `main`.
