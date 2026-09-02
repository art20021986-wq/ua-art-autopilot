# ACCEPTANCE_TEST_PLAN.md — TASK 105 Phase 0

## Purpose
Define how Phase 0 completion is verified, and pre-define how Phase 1 (sandbox/shadow orchestrator) will be tested before any production exposure.

## Phase 0 acceptance checks (self-assessment against task's own completion criteria)
| Criterion (from task scope) | Status | Evidence |
|---|---|---|
| 100% of current workflows inventoried and classified | PARTIAL — provisional inventory produced; live listing confirmation pending (BLOCKER-INV-01) | WORKFLOW_INVENTORY.md |
| Production writers and shared dependencies explicitly identified | YES (to the extent knowable without live YAML) | DEPENDENCY_MAP.md, WORKFLOW_INVENTORY.md |
| Target 6–8 workflow architecture proposed | YES | TARGET_ARCHITECTURE.md |
| Migration is reversible and staged | YES | MIGRATION_PLAN.md |
| No production files/settings changed | YES | this task only wrote files under cloud/ |
| Report contains evidence paths and unresolved blockers | YES | PHASE0_REPORT.md, RISK_REGISTER.md |
| Owner-facing reply states audit/sandbox-prep, not deployment | YES | cloud/owner_reply.md |

## Phase 1 pre-implementation test plan (proposal, not executed here)
1. **Classification determinism test** — feed the orchestrator a fixed set of synthetic `tasks/task_NNN.md` fixtures covering FAST/STANDARD/CRITICAL boundary cases; assert identical classification across 10 repeated runs (mirrors the byte-identical repeat-run discipline used in TASK021's 10x41 offline suite per shared memory REC-0013).
2. **Shadow-mode non-interference test** — run `orchestrator_dispatch.yml` in shadow mode alongside the legacy path for at least N real tasks; assert zero writes outside `cloud/` from the shadow path.
3. **Resource-lock isolation test** — in a sandbox queue, simulate two tasks with disjoint lock keys and assert they do not block each other; simulate two tasks with the same lock key and assert strict serialization is preserved.
4. **State machine additive-compatibility test** — assert legacy `cloud/latest_status.md` consumers (Codex audit step) can still parse status files after new fields are added.
5. **ROOT_CAUSE_MODE trigger test** — simulate 3 repeated identical failure signatures and assert automated retries stop and a human-reviewable root-cause marker is written, with no further automated production-adjacent action taken.
6. **Rollback drill** — for any Stage 4+ change, perform a rollback drill in sandbox (flip feature flag off / delete new workflow file) and confirm legacy behavior is fully restored with no residual state.

## Exit criteria for moving from Phase 1 sandbox to any production exposure
- All six Phase 1 tests above pass with reproducible evidence (paths, logs).
- Explicit owner approval recorded (mirroring how this task itself required "Approved by owner on 2026-09-01").
- BLOCKER-INV-01, BLOCKER-DEP-01, and BLOCKER-RC-01 from Phase 0 are resolved with verified (not provisional) evidence.
