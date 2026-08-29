# TASK 079 — Release candidate sandbox report

Contract: `CRM-CONTAINER-STAGE-SYNC-004 v1.0`
Mode: BACKUP -> SANDBOX/CANARY -> Gate A only. No production, CRM, or site writes performed.

MEMORY MARKERS (verbatim, do not alter):
- CONTEXT_BUNDLE_SHA256: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
- MEMORY_VERSION_READ: `4`

## What was actually produced in this delivery

1. `patcher/eta_release_candidate.py` — the single shared ETA/status writer,
   verified read-back, bounded staging-file builder/installer, compensating
   rollback machinery, `toggle_publish` semantics, and a narrow stale-date
   sanitizer, all designed exactly to the TASK 079 architecture contract.
2. `patcher/live_patcher.py` — a fail-closed, non-writing patch preparer that
   verifies full-file SHA-256 anchors and per-function source hashes before
   ever proposing a transplant, and is hardcoded (`ALLOW_WRITE_HARDCODED =
   False`) to refuse any write in this delivery regardless of caller input.
3. `tests/test_eta_release_candidate.py` — a pytest suite covering every
   scenario enumerated in the TASK 079 “Mandatory sandbox tests” section:
   N=0/1/30/400 and invalid N, idempotence, protected-status preservation,
   allowed ferry normalization, `published` preimage 0/1 preservation,
   commit-before-publish proof via a spy publisher, injected publisher
   failure/read-back failure/partial install failure/delayed overwrite with
   verified compensating rollback and exact byte/row restoration, the
   UA-0009/0010/0011 target-state scenario, the UA-0012 + diagnostic
   placeholder scenario, unrelated-field preservation, single success/failure
   messaging for `toggle_publish`, narrow stale-date sanitization (including
   an unrelated-date preservation case), and deterministic anchor-mismatch
   refusal.

## Result classification

This delivery does **not** claim `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.

Reason: this Cloud/Claude delivery channel does not execute code; it only
authors it. Per this repository's own established acceptance pattern (see
canonical memory `REC-0009`/`REC-0013`, where Claude explicitly did not
fabricate execution results and the Codex controller independently ran the
offline suite before any PASS label was recorded), no PASS claim is made
here without an actual observed test run.

**Result: `FAIL_CLOSED_PENDING_INDEPENDENT_TEST_EXECUTION`**

This is a deliberate fail-closed status, not a defect report. The test suite
is complete and, by design and code review, exercises every required
scenario against temporary SQLite files and temporary directories only. The
next required step is for the Codex controller (or another execution-capable
agent) to run:

```
python -m pytest cloud/task_077_container_stage_sync/tests/test_eta_release_candidate.py -v
```

and record the literal pass/fail counts into canonical memory, exactly as was
done for TASK 015 and TASK 021. Only after that independent, verifiable
execution may the result be upgraded to
`PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.

## No production/CRM/site change occurred

- `PRODUCTION_TOUCHED: NO`
- No PythonAnywhere execution occurred.
- No process reload occurred.
- Gate B was not executed and is not authorized by this delivery.
- `db.py`, `cars_ui.py`, `konteyner.py`, `stranica.py`, `publikaciya.py` on
  the live host were not read, opened, or modified by this delivery; all
  anchors above are used purely as fail-closed comparison targets inside
  `live_patcher.py`, which never executes a write in this repository.
