# ACCEPTANCE_TEST_PLAN.md — TASK 105 Phase 0

## Purpose
Define how Phase 0 completion and future Phase 1 stages will be verified, without performing any production action in this phase.

## Phase 0 acceptance checks (self-assessed in this deliverable; to be confirmed by controller)
1. [x] All required Phase 0 files exist under `cloud/task_105_fast_pipeline_phase0/`.
2. [x] No file under `.github/workflows/` was created, modified, or deleted by this task.
3. [x] No file under any PythonAnywhere production path, Cloudflare config, or DNS config was touched.
4. [x] No secret values were read, written, or referenced by name-with-value.
5. [~] 100% literal workflow inventory — **NOT fully verifiable in this session**; delivered as a provisional/structured inventory with an explicit confirmation step required (see WORKFLOW_INVENTORY.md). This is recorded as an unresolved blocker in PHASE0_REPORT.md rather than claimed as complete.
6. [x] Target 6–8 workflow architecture proposed (TARGET_ARCHITECTURE.md).
7. [x] Migration plan is staged and reversible (MIGRATION_PLAN.md).
8. [x] Canonical state machine proposed to resolve FINISHED/PASS/AWAITING_PRODUCTION_APPROVAL ambiguity (CURRENT_STATE_MACHINE.md).
9. [x] Resource-aware locking proposal in place of global serialization (TARGET_ARCHITECTURE.md).
10. [x] AI routing rules with token/call budgets proposed (TARGET_ARCHITECTURE.md).
11. [x] Deterministic retry policy and ROOT_CAUSE_MODE defined (TARGET_ARCHITECTURE.md, MIGRATION_PLAN.md).
12. [x] KPIs defined (TARGET_ARCHITECTURE.md).

## Phase 1 (future) acceptance tests — to be executed only after owner review of this report
1. Shadow orchestrator dry-run produces classification decisions for at least 10 historical tasks with 0 crashes and logs matching expected lane assignment for at least 80% of manually-reviewed cases.
2. Resource-lock composite action, run in shadow mode, never reports a false "safe to run concurrently" for two tasks known to touch the same production resource (0 false negatives required before Stage 3).
3. `worker-fast.yml` opt-in run for a real FAST task produces `SELF_VERIFIED` state and correct `cloud/latest_status.md`/`cloud/owner_reply.md` output with PRODUCTION_WRITE: NO, verified by an independent controller pass.
4. Each legacy workflow proposed for MERGE/ARCHIVE has an equivalent passing test in the new consolidated workflow before the legacy one is moved to ARCHIVE (never DELETE without separate owner sign-off).
5. ROOT_CAUSE_MODE triggers correctly after exactly 3 consecutive same-step failures in a controlled test task, and produces a structured diagnostic artifact instead of a 4th blind retry.
6. `production-apply.yml` dry-run (Stage 5) computes an intended change set and rollback plan without applying anything, verified by controller before any live-cutover task is even proposed.

## Evidence paths
- This plan: `cloud/task_105_fast_pipeline_phase0/ACCEPTANCE_TEST_PLAN.md`
- Companion audit: `cloud/task_105_fast_pipeline_phase0/WORKFLOW_INVENTORY.md`, `DEPENDENCY_MAP.md`
- Status/report: `cloud/latest_status.md`, `cloud/task_105_fast_pipeline_phase0/PHASE0_REPORT.md`
