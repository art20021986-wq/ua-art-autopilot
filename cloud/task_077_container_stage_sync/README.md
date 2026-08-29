# TASK 079 — Finish TASK 077 ETA/status synchronization release candidate

Contract: `CRM-CONTAINER-STAGE-SYNC-004 v1.0`

MEMORY MARKERS (verbatim):
- CONTEXT_BUNDLE_SHA256: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
- MEMORY_VERSION_READ: `4`

## Scope of this delivery

This package finishes the design/implementation phase of the ETA/status
synchronization fix proven necessary by TASK 076 and TASK 077 evidence. It:

- implements one shared ETA writer (`eta_release_candidate.apply_eta_change`)
  intended to eventually replace the two divergent live call sites
  (`konteyner.prinyat`, `cars_ui.apply_value`);
- implements verified staged publication with atomic install, preimage
  capture, and compensating rollback with byte-for-byte verification;
- implements `toggle_publish` semantics that never emit a success message
  without a verified publisher PASS and always restore the `published`
  preimage on failure;
- implements a narrow stale-arrival-sentence sanitizer that only removes a
  sentence that is simultaneously about arrival/delivery AND contains an
  independent calendar date, leaving all unrelated dates and content intact;
- implements `live_patcher.py`, a fail-closed, non-writing tool that will,
  after separate Gate B approval, verify full-file and per-function source
  anchors before any real transplant is even considered, and refuses
  duplicate/unexpected function definitions.

## What this delivery does NOT do

- It does not touch any production, CRM, or PythonAnywhere path.
- It does not execute Gate B.
- It does not claim any test PASS without an actual observed run (see
  `sandbox/release_candidate_report.md`).
- It does not modify `cloud/task_078_voice_watchdog/`.
- It does not create a second workflow watchdog; the existing
  `.github/workflows/safe_workflow_watchdog.yml` already covers the
  `task077-container-stage-sync-gate-a` workflow name.

## File map

- `patcher/eta_release_candidate.py` — shared writer, staging, rollback, sanitizer.
- `patcher/live_patcher.py` — fail-closed anchor-verifying patch preparer (no writes).
- `tests/test_eta_release_candidate.py` — full sandbox pytest suite.
- `sandbox/release_candidate_report.md` — honest, non-fabricated test-result status.
- `evidence/gate_a_findings.md` — restated live defect findings used as the basis for this design.
- `gate_b_manual_workflow.md` — prepared-but-unexecuted Gate B plan with the exact owner token.

## How an owner/controller can validate this before any Gate B step

```
python -m pytest cloud/task_077_container_stage_sync/tests/test_eta_release_candidate.py -v
```

Run this in a disposable environment. No production credentials, hosts, or
CRM data are required or touched.
