# MIGRATION PLAN — TASK105

## Phase 0 — completed by this audit

- Inventory and classify all 129 workflows.
- Map production, PythonAnywhere, Anthropic, watchdog, queue and retry capabilities.
- Define canonical state machine and target seven-workflow architecture.
- No production write.

## Phase 1 — sandbox orchestrator

- Add state schema, classifier, resource-lock planner and receipt validator.
- No deployment capability.
- Run unit tests and failure injection locally/GitHub only.

## Phase 2 — shadow mode

- Feed real task metadata to old and new routers.
- New router makes decisions but does not execute production.
- Compare classification, required locks and expected stages.

## Phase 3 — FAST canary

- 20 synthetic tasks: 20/20 PASS.
- 3 owner-approved low-risk production changes with backup and live smoke.
- Automatic rollback on any protected diff.

## Phase 4 — STANDARD canary

- 10 sandbox tasks and 3 controlled production tasks.
- Verify CRM/card/counter regression profiles.

## Phase 5 — CRITICAL adapter

- Preserve existing strict gates behind one parameterized critical workflow.
- No reduction of security controls until equivalent evidence exists.

## Phase 6 — consolidation

Current classification baseline:
- KEEP: 4
- MERGE: 92
- ARCHIVE: 33
- DELETE_CANDIDATE: 0

Archive only after replacement parity, dependency scan, rollback drill and owner approval.
Do not delete history during the migration.
