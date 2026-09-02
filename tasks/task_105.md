# TASK 105 — UA-ART-FAST-PIPELINE-001 Phase 0

## Owner approval
Approved by owner on 2026-09-01.

## Scope
Implement **Phase 0 only** of UA-ART-FAST-PIPELINE-001: full read-only audit and sandbox preparation. Do not modify production, CRM runtime, PythonAnywhere production files, Cloudflare production configuration, DNS, or existing live publication behavior.

## Objective
Produce a verified architecture inventory and migration plan for a new central UA ART Task Orchestrator that classifies work into FAST / STANDARD / CRITICAL and reduces unnecessary GitHub Actions, AI calls, retries, and global queue blocking while preserving rollback and production safety.

## Mandatory audit
1. Inventory all `.github/workflows/*.yml` and `.yaml`.
2. Classify every workflow: KEEP / MERGE / ARCHIVE / DELETE_CANDIDATE.
3. Map triggers, concurrency groups, dependencies, production-write capability, PythonAnywhere transport, Claude/Anthropic usage, watchdogs, queue gates, retry/recovery behavior, and owner-approval gates.
4. Identify duplicate or overlapping workflows and any task-specific workflows that should become parameterized shared pipelines.
5. Audit `automation/production_queue.py`, Claude worker/launcher/transport, PythonAnywhere sync/production paths, and status/receipt files.
6. Use TASK096 v3-v8 as a root-cause anti-pattern: identify why repeated wrapper/transport/controller/API repairs were needed and which failures should move to deterministic preflight.
7. Confirm current ambiguity around FINISHED / PASS / AWAITING_PRODUCTION_APPROVAL and propose one canonical state machine.
8. Propose resource-aware locking instead of global production serialization.
9. Propose AI routing rules: NO_AI / GPT_PRIMARY / CLAUDE_REVIEW / CLAUDE_PRIMARY / DUAL_REVIEW, with token/call budgets.
10. Define deterministic retry policy and ROOT_CAUSE_MODE after repeated logical failures.
11. Define measurable KPIs: task-to-finished time, queue wait, GitHub runs/task, AI calls/task, retries/task, false-finished count, rollback rate.

## Required deliverables
Create under `cloud/task_105_fast_pipeline_phase0/`:
- `WORKFLOW_INVENTORY.md`
- `DEPENDENCY_MAP.md`
- `ROOT_CAUSE_AUDIT_TASK096.md`
- `CURRENT_STATE_MACHINE.md`
- `TARGET_ARCHITECTURE.md`
- `MIGRATION_PLAN.md`
- `RISK_REGISTER.md`
- `ACCEPTANCE_TEST_PLAN.md`
- `PHASE0_REPORT.md`

Also update:
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

## Hard safety boundaries
- PRODUCTION_WRITE: NO
- CRM_WRITE: NO
- PYTHONANYWHERE_PRODUCTION_WRITE: NO
- CLOUDFLARE_PRODUCTION_WRITE: NO
- DNS_WRITE: NO
- No deletion of existing workflows.
- No disabling existing workflows.
- No changing secrets.
- No direct deployment.
- No merge to main from this task branch.

## Phase 0 completion criteria
Phase 0 is DONE only when:
- 100% of current workflows are inventoried and classified;
- production writers and shared dependencies are explicitly identified;
- a target 6-8 workflow architecture is proposed;
- migration is reversible and staged;
- no production files/settings were changed;
- report contains evidence paths and unresolved blockers;
- owner-facing reply clearly states that this is an audit/sandbox-preparation result, NOT production deployment.

## Next phase
Do not start Phase 1 implementation until Phase 0 report is reviewed. Phase 1 will build the orchestrator in sandbox/shadow mode only.
