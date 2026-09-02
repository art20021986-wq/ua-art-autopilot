# MIGRATION_PLAN.md — TASK 105 Phase 0 (proposal, staged, reversible)

## Guiding constraint
Every stage below must be reversible without touching production, and each stage must be independently verifiable before the next stage starts. No stage in this plan is executed by Phase 0; Phase 0 only proposes and sequences them.

## Stage 0 (this task): Audit + sandbox prep
- Deliverables: this directory (`cloud/task_105_fast_pipeline_phase0/`).
- Rollback: trivial — these are new files under `cloud/`; deleting the branch fully reverts with zero production impact.

## Stage 1: Confirm inventory with live data (blocking prerequisite for all later stages)
- Codex/owner supplies a verified `git ls-tree`/directory listing of `.github/workflows/` and the actual TASK096 v3–v8 diffs.
- Upgrade WORKFLOW_INVENTORY.md and ROOT_CAUSE_AUDIT_TASK096.md from provisional to verified.
- Rollback: N/A (read-only).

## Stage 2: Build orchestrator in shadow mode (Phase 1 scope, not this task)
- New `orchestrator_dispatch.yml` is added **alongside** existing workflows (none removed/disabled).
- Orchestrator only *classifies and logs* (FAST/STANDARD/CRITICAL) without taking any action — pure shadow/dry-run, writing its decision to a new `cloud/` report file for comparison against what actually happened.
- Rollback: delete the new workflow file; zero effect on existing pipeline since nothing was disabled.

## Stage 3: Route FAST tasks only, in parallel with legacy path
- For a small, explicitly owner-approved allow-list of task types (e.g., doc-only `cloud/` audits like this one), allow the new `fast_lane.yml` to run *in addition to* the legacy path, then diff outcomes.
- Legacy path remains authoritative; new path is advisory only at this stage.
- Rollback: remove task type from allow-list.

## Stage 4: Introduce resource-aware locking behind a feature flag
- Add per-resource lock keys to `automation/production_queue.py` behind a flag defaulting to OFF (legacy global lock remains default behavior).
- Test in a non-production sandbox queue only.
- Rollback: flip flag off; legacy global lock code path is untouched and remains the default.

## Stage 5: Canonical state machine adoption
- Add new fields to a *new* status schema version (do not silently redefine existing `CLAUDE_STATUS` semantics) so both old and new consumers keep working during transition.
- Rollback: consumers that don't understand new fields simply ignore them (additive schema change).

## Stage 6: Deterministic retry / ROOT_CAUSE_MODE enforcement
- Enable only after Stage 5's state machine is validated end-to-end in shadow mode.
- Rollback: disable ROOT_CAUSE_MODE trigger, fall back to prior manual-escalation behavior.

## Stage 7: Deprecate/ARCHIVE task-specific one-off workflows
- Only after Stages 2–6 have run successfully for an owner-defined observation period, and only with explicit owner approval, move DELETE_CANDIDATE workflows (per WORKFLOW_INVENTORY.md) to an `archive/` note — task instructions forbid actually deleting/disabling workflows in this task; this stage is future work requiring its own owner-approved task.
- Rollback: N/A at this stage since nothing is deleted without a separate future approval.

## Explicit statement
No stage above was executed. This is a sequencing proposal only, gated stage-by-stage on independent verification and, where noted, explicit owner approval.
