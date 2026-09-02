# ROOT_CAUSE_AUDIT_TASK096.md — TASK 105 Phase 0

## Objective
Use TASK096 v3–v8 as the anti-pattern reference to identify why repeated wrapper/transport/controller/API repairs were required, and which of those failure classes should be converted into deterministic preflight checks instead of reactive, task-specific repair workflows.

## Observed pattern (from task history / protocol narrative)
TASK096 required at least six iterations (v3 through v8) to reach a working state. Each iteration appears to have repaired one of: the Claude wrapper, the transport layer to PythonAnywhere, the controller logic, or an API integration point. This is a classic symptom of **reactive patching without a deterministic preflight gate**: each failure was discovered only at runtime, in production-adjacent conditions, rather than caught by a repeatable, offline, pre-execution check.

## Root cause classes identified
1. **No deterministic preflight validation of the transport layer.** Failures in reaching PythonAnywhere (auth, path, encoding, timeout) were discovered live rather than through a standalone, side-effect-free connectivity/contract test run before the real task executes.
2. **No single canonical wrapper/launcher contract.** Because task-specific workflows were created per incident (see WORKFLOW_INVENTORY.md DELETE_CANDIDATE rows), each wrapper repair fixed the symptom for that one workflow file rather than the shared launcher code, so the same class of bug could resurface in a different task-specific workflow.
3. **No controller-level idempotency/verification step.** Repeated "controller repairs" suggest the controller's acceptance criteria were not deterministic (e.g., varying pass counts, inconsistent hash verification) rather than the underlying production logic changing each time.
4. **API integration drift not caught by static checks.** Each API-related fix implies the integration surface (parameters, response shape, auth) was validated only by full end-to-end execution, which is expensive (GitHub Actions minutes, AI calls) and slow to detect.
5. **Absence of a single state machine.** Because FINISHED / PASS / AWAITING_PRODUCTION_APPROVAL were not strictly defined (task scope point 7), some "repairs" in v3–v8 may have actually been re-classifications of an already-working state rather than genuine functional bugs — inflating the retry count.

## Recommendation: move to deterministic preflight
Each root cause class above maps to a **preflight check that runs before any AI call or production-adjacent action**, is side-effect-free, deterministic (same input → same output), and fast:
- Preflight-1: Transport connectivity/contract check (no data write) — replaces class 1.
- Preflight-2: Single shared launcher/wrapper contract test (byte-identical input/output fixtures) — replaces class 2.
- Preflight-3: Controller acceptance criteria expressed as a fixed, versioned checklist rather than free-form narrative — replaces class 3.
- Preflight-4: API contract snapshot test (schema/response shape) run offline — replaces class 4.
- Preflight-5: Canonical state machine (see CURRENT_STATE_MACHINE.md / TARGET_ARCHITECTURE.md) enforced by the orchestrator, not by individual workflows — replaces class 5.

## Unresolved blocker
BLOCKER-RC-01: The literal commit/PR history for TASK096 v3–v8 was not independently re-diffed byte-for-byte inside this session; this audit is based on the pattern description supplied in the task scope and general repository protocol knowledge. Codex should attach the actual TASK096 v3–v8 diffs/logs in a follow-up round so this document can be upgraded from pattern-inference to verified root cause with line-level evidence.
