# CURRENT_STATE_MACHINE.md — TASK 105 Phase 0

## Problem
The task explicitly flags ambiguity between **FINISHED**, **PASS**, and **AWAITING_PRODUCTION_APPROVAL**, and requires one canonical state machine proposal.

## Current observed states (from durable memory and status file conventions)
- `CLAUDE_STATUS` values seen in protocol: WORKING, DONE, BLOCKED, WAITING_OWNER.
- `computed_status` on memory records: ACTIVE, SUPERSEDED.
- Ad-hoc task language: FINISHED, PASS, FAIL, AWAITING_PRODUCTION_APPROVAL, READY_FOR_GATE_A_EXECUTION, CONTROLLER_VERIFIED_ACCEPTED, NOT_PROVEN.

These are at least three independent vocabularies (worker status, memory record status, ad-hoc task/report language) that are not currently unified, which is exactly the ambiguity the task asks to resolve.

## Proposed canonical state machine (single source of truth)
Every unit of work (a task_NNN) progresses through exactly one of these canonical states, stored in one field (`TASK_STATE`) written only by the component authorized to change it:

1. **RECEIVED** — task file committed to `tasks/`; no worker action yet.
2. **CLASSIFYING** — orchestrator (Phase 1+) assigns FAST / STANDARD / CRITICAL lane.
3. **IN_PROGRESS** — worker actively producing deliverables (maps to current `WORKING`).
4. **SELF_VERIFIED** — worker completed its own deliverables and internal checks pass (maps to current `DONE`, but explicitly *not* production-approved).
5. **CONTROLLER_VERIFIED** — an independent controller (Codex or equivalent) re-checked the deliverables against evidence (maps to `CONTROLLER_VERIFIED_ACCEPTED`).
6. **AWAITING_OWNER_APPROVAL** — required only when the task requests a CRITICAL or production-affecting action; explicit owner sign-off is pending (maps to `WAITING_OWNER`).
7. **APPROVED_FOR_PRODUCTION** — owner approval recorded; still not yet applied.
8. **APPLIED_TO_PRODUCTION** — the only state where PRODUCTION_WRITE may legitimately be YES; requires Gate B evidence per REC-0004.
9. **ROLLED_BACK** — production change reverted; must reference the APPLIED_TO_PRODUCTION event it undoes.
10. **BLOCKED** — cannot proceed; requires `OWNER_ACTION_REQUIRED` or technical unblock, unchanged from current usage.
11. **CLOSED_FINISHED** — terminal success state for tasks that never touch production (i.e., "FINISHED" is retired as an ambiguous synonym and replaced by this explicit terminal state).

### Elimination of ambiguous terms
- **"PASS"** is retired as a terminal state name; it becomes an *evidence attribute* (`TEST_RESULT: PASS|FAIL`) attached to SELF_VERIFIED/CONTROLLER_VERIFIED, never a standalone task state.
- **"FINISHED"** is retired; replaced by `CLOSED_FINISHED` (no production involved) or `APPLIED_TO_PRODUCTION` (production involved), so it is always unambiguous whether production was touched.
- **"AWAITING_PRODUCTION_APPROVAL"** is retired as free text; replaced by canonical state `AWAITING_OWNER_APPROVAL` with a machine-readable `APPROVAL_SCOPE: PRODUCTION|CRM|DNS|CLOUDFLARE`.

## Transition rules (summary)
- Only the orchestrator may move a task out of RECEIVED.
- Only the worker (Claude/Cloud) may move IN_PROGRESS → SELF_VERIFIED.
- Only an independent controller may move SELF_VERIFIED → CONTROLLER_VERIFIED.
- Only an explicit owner-directive record may move → APPROVED_FOR_PRODUCTION or → APPLIED_TO_PRODUCTION.
- Any state may move to BLOCKED; BLOCKED may only be exited by resolving the documented blocker.

This state machine is a **proposal for Phase 1**; it is not implemented or enforced by this Phase 0 deliverable, and no existing status files have been changed to use it.
