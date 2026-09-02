# CURRENT_STATE_MACHINE.md — TASK 105 Phase 0

## Problem statement
The task scope (point 7) explicitly flags ambiguity between **FINISHED**, **PASS**, and **AWAITING_PRODUCTION_APPROVAL**. Based on protocol documents and task history, these three terms are currently used inconsistently across different workflows/reports:

- **FINISHED** has been used to mean "the worker completed its assigned steps" — but this does not distinguish between "deliverables written to cloud/" and "changes actually validated/accepted by a controller."
- **PASS** has been used by an independent controller (see REC-0011, REC-0013 in shared memory) to mean "tests/acceptance criteria were independently verified," which is a stronger claim than FINISHED.
- **AWAITING_PRODUCTION_APPROVAL** is used when a change is technically ready but requires an owner-bound Gate B/Gate A step before touching production — but nothing currently prevents a workflow from reporting FINISHED while a production write is still pending owner approval, which is the exact ambiguity that risks a "false-finished" KPI event (task scope point 11).

## Current (as-observed) informal states
1. `WORKING` — Claude/worker actively producing output.
2. `DONE` (worker-reported) — worker believes its own scope is complete. This is a **self-report**, not independent verification.
3. `PASS` (controller-verified) — an independent controller (Codex or automated evidence) has re-run tests/checks and confirms the self-report. Per shared memory REC-0011/REC-0013, this has historically required a separate manual/automated re-verification pass, not part of the original workflow.
4. `AWAITING_PRODUCTION_APPROVAL` — used ad hoc when a production write is contemplated; not tied to a single canonical flag in `cloud/latest_status.md` (that file only has `OWNER_ACTION_REQUIRED: YES|NO`, which conflates "need an answer to a question" with "need Gate B approval for a production write").
5. `BLOCKED` / `WAITING_OWNER` — both exist in `CLAUDE_STATUS` enum today, without a clear rule for which one applies when the blocker is technical vs. approval-related.

## Root ambiguity
There is currently **no single canonical field** that separates:
- (a) "worker self-report of completion" from
- (b) "independent verification/controller PASS" from
- (c) "owner Gate B production-approval pending."

All three get folded into overlapping status vocabulary (`CLAUDE_STATUS`, ad hoc "PASS" mentions in memory records, `OWNER_ACTION_REQUIRED`). This is exactly the condition that produces the "false-finished count" KPI risk named in the task scope.

## Proposed canonical state machine (proposal only — not implemented in Phase 0)
```
RECEIVED -> CLASSIFIED(FAST|STANDARD|CRITICAL)
         -> IN_PROGRESS
         -> SELF_REPORTED_COMPLETE      (worker says done; NOT trusted alone)
         -> VERIFIED_PASS               (independent/automated re-check confirms)
         -> AWAITING_OWNER_APPROVAL     (only reached if task requires production write; explicit Gate)
         -> APPROVED_FOR_PRODUCTION     (owner explicitly approved; Gate B)
         -> FINISHED                    (terminal state; only reachable via VERIFIED_PASS, and via APPROVED_FOR_PRODUCTION if production write was required)
         -> ROLLED_BACK                 (terminal, exception path)
         -> BLOCKED                     (technical blocker, no owner action needed yet)
         -> WAITING_OWNER                (non-approval question needed)
```
Key rule: **FINISHED is only ever reachable through VERIFIED_PASS**, and if the task scope included any production write, FINISHED additionally requires APPROVED_FOR_PRODUCTION. This directly resolves the ambiguity named in task scope point 7 and is detailed further in TARGET_ARCHITECTURE.md.

This document is a **proposal for Phase 1**; no state machine changes were implemented in Phase 0.
