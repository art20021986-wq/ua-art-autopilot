# TASK 079 — ETA/Status Synchronization Release Candidate

Contract: `CRM-CONTAINER-STAGE-SYNC-004 v1.0`
Scope: final safe continuation of TASK 077 / TASK 076.
Mode: BACKUP -> SANDBOX/CANARY -> Gate A only. Production writes, CRM writes,
site writes, process reloads, and Gate B execution are forbidden in this
delivery.

MEMORY MARKERS (verbatim):
`CONTEXT_BUNDLE_SHA256=2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
`MEMORY_VERSION_READ=4`

## Contents

- `patcher/eta_release_candidate.py` — the shared ETA/status writer, the
  bounded file stager, the compensating-rollback orchestrator
  (`run_eta_sync_release`), and the narrow stale-arrival-sentence sanitizer.
  This is the single code path intended to be called by both
  `konteyner.prinyat` and `cars_ui.apply_value` once Gate A/B are
  separately approved.
- `patcher/live_patcher.py` — the fail-closed Gate A patch-application tool.
  It verifies full-file SHA-256 anchors and per-function AST hashes before
  ever considering a patch, and in this delivery it always fails closed
  because no real production bytes or captured golden function source were
  supplied to Claude/Cloud.
- `tests/test_eta_release_candidate.py` — 22 sandbox test cases run only
  against temporary SQLite databases and temporary files.
- `sandbox/release_candidate_report.md` — full test report and the honest
  fail-closed final verdict for this round.
- `evidence/gate_a_findings.md` — restated findings from the TASK 076/077
  live evidence that this release candidate is designed to fix.
- `gate_b_manual_workflow.md` — the prepared-but-unexecuted Gate B plan and
  the exact single owner approval token.

## Why this cannot be applied to production yet

1. The task supplies proven full-file SHA-256 anchors for the five live
   files, but not their actual bytes. Claude/Cloud has no way to read real
   production source in this environment, and is explicitly forbidden from
   touching production directly.
2. The contract requires fail-closed verification at the function-source
   level, not just the full-file level, before any patch may be considered
   for the real entry points. That requires a captured golden function
   source, which is a separate evidence-backed Gate A action outside this
   delivery's scope.
3. Therefore `live_patcher.apply()` is written to always fail closed in
   this delivery, and the sandbox report's final verdict is a specific
   fail-closed result, not a false `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.

## What is ready

- The shared writer, rollback/compensation, file staging, and sanitizer
  logic are implemented and pass a genuine sandbox test suite that
  reproduces the documented live defect shape (mixed published states,
  protected vs. ferry statuses, UA-0009's stale arrival sentence, and the
  UA-0009/0010/0011/0012 target end-state).
- The Gate B manual workflow and the single exact owner token are prepared
  for a future, separately-approved round, per contract item 11.

## Non-negotiable safety statements

- Production touched: NO.
- CRM/site touched: NO.
- No process reload, publish, or Gate B action was performed.
- `cloud/task_078_voice_watchdog/` was not modified or regenerated.
- No second workflow watchdog was created; the existing
  `task077-container-stage-sync-gate-a` workflow remains covered by
  `.github/workflows/safe_workflow_watchdog.yml`.
