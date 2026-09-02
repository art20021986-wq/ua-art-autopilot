# ROOT_CAUSE_AUDIT_TASK096.md — TASK 105 Phase 0

## Objective
Use TASK096 v3–v8 (repeated wrapper/transport/controller/API repair cycles) as the anti-pattern case study required by the task, and identify which classes of failure should move to deterministic preflight instead of reactive per-incident repair.

## Observed pattern (from task naming and repetition alone — v3 through v8)
A task that required **six or more repair rounds** on the same functional area (wrapper, transport, controller, API) is itself the primary evidence of a systemic problem: the failure was being diagnosed and patched *after* execution, one symptom at a time, rather than being caught by a *pre-execution contract check*.

## Likely root-cause categories (standard failure modes for this kind of repeated-repair signature)
1. **Non-deterministic environment assumptions** — the wrapper/launcher likely depended on implicit state (working directory, environment variables, file existence) that was not validated before use, so each new repair fixed one instance without adding a general guard.
2. **Transport contract drift** — the transport layer (Claude worker ↔ controller ↔ API) probably had no schema/contract test, so changes on one side (e.g. API response shape, controller expectations) silently broke the other side until a human/AI noticed at runtime.
3. **Retry-without-diagnosis** — repeated rounds (v3→v8) suggest retries were applied before root cause was isolated, so the same class of bug reappeared under a new surface symptom each time.
4. **No preflight validation gate** — nothing appears to have blocked execution *before* wrapper/transport/controller/API were invoked to confirm required secrets, file paths, and expected message formats existed and matched.
5. **Ambiguous success criteria** — without a single canonical state machine (see CURRENT_STATE_MACHINE.md), a "fix" could be marked done based on partial evidence, only to be reopened in the next round.

## What should move to deterministic preflight (Phase 1 target, not implemented now)
- Static schema validation of the task file, the worker's expected input contract, and the controller's expected output contract, run **before** any AI call or production-adjacent action.
- A dry-run/self-test mode for the transport and controller that can be executed in CI without touching PythonAnywhere or Anthropic APIs, to catch structural breakage early.
- A single ROOT_CAUSE_MODE trigger (see MIGRATION_PLAN.md) that activates after N consecutive logical failures on the same task, switching from "retry" to "deterministic diagnosis" (collect and report structured failure evidence instead of re-attempting the same action).

## Verification gap
The worker did not have direct access to the literal TASK096 v3–v8 diff history or workflow run logs in this session, so the specific line-level bugs cannot be enumerated here. This audit is a structural root-cause analysis based on the repetition pattern and the task's own framing ("root-cause anti-pattern"), and should be cross-checked against the actual TASK096 branch history before Phase 1 begins.
