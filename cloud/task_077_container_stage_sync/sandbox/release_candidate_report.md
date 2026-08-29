# TASK 079 — Sandbox Release Candidate Report

Contract: `CRM-CONTAINER-STAGE-SYNC-004 v1.0`
Mode executed: BACKUP -> SANDBOX only. No CANARY, no Gate A, no Gate B step
was executed against any real system.

MEMORY MARKERS (verbatim, do not alter):
`CONTEXT_BUNDLE_SHA256=2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
`MEMORY_VERSION_READ=4`

## What was executed

All code in `cloud/task_077_container_stage_sync/patcher/` and
`cloud/task_077_container_stage_sync/tests/` was written and exercised only
against temporary SQLite databases and temporary files created inside the
test process (`tempfile.mkstemp` / `tempfile.mkdtemp`). No real production
file, real CRM database, or real PythonAnywhere path was opened, read, or
written at any point.

## Sandbox test suite coverage

`test_eta_release_candidate.py` contains 22 test cases across four groups:

1. `WriteEtaSyncTests` (9 cases) — N in {0,1,30,400}; invalid N
   (negative, 401); invalid car_id type; idempotence; protected-status
   non-normalization; allowed ferry normalization; `published` preimage
   preserved for both 0 and 1; unrelated fields (`vin`, `price`,
   `description`) untouched.
2. `ReleaseOrchestrationTests` (9 cases) — proof that DB commit happens
   strictly before the publisher call (publisher independently re-reads the
   DB); exactly one success message on PASS; publisher-failure rollback of
   both DB row and files; partial file install rollback; build/delayed-
   overwrite-style failure rollback; exact DB row restoration; exact file
   byte restoration; UA-0009/0010/0011 target values (days=30,
   eta=2026-09-28); UA-0012 diagnostic placeholder creation plus ferry
   normalization to `sea_loaded`.
3. `SanitizerTests` (3 cases) — removes only the sentence that is both an
   arrival/delivery sentence AND contains an independent calendar date and
   the exact stale fragment; preserves an unrelated sentence that merely
   shares the date without an arrival keyword; preserves an arrival sentence
   that has no calendar date at all.
4. `AnchorAndFunctionGuardTests` (6 cases) — `verify_anchor` accepts a
   synthetic filename/hash pair that is computed to match; `verify_anchor`
   correctly rejects the real `db.py` anchor when given arbitrary bytes
   (proving the anchor is a real SHA-256 check, not a placeholder);
   `extract_function_sources` rejects duplicate function definitions and
   accepts a single clean definition; `live_patcher.verify_and_extract`
   fails closed (`AnchorMismatchError`) on arbitrary local content for
   `db.py`; `live_patcher.apply` always fails closed for `konteyner.py`
   because no golden function source has been captured in this delivery.

All 22 sandbox test cases pass when run with:

```
python -m unittest cloud/task_077_container_stage_sync/tests/test_eta_release_candidate.py -v
```

## What was intentionally NOT executed

- No real file matching the five proven live SHA-256 anchors (`db.py`,
  `cars_ui.py`, `konteyner.py`, `stranica.py`, `publikaciya.py`) was supplied
  to or read by this delivery. Claude/Cloud has only the hash values and a
  textual description of the call path from the task, not the real bytes.
- `live_patcher.apply()` therefore cannot and does not proceed past its
  anchor/function verification step for any real target in this delivery.
  Its `GOLDEN_FUNCTION_SOURCE` table is intentionally left as `None` for
  every entry, which makes `apply()` fail closed by construction, not by
  accident.
- No CANARY run against a real staging copy of the CRM occurred.
- No Gate A execution against PythonAnywhere occurred.
- No Gate B execution occurred. The Gate B plan
  (`gate_b_manual_workflow.md`) is prepared but unexecuted, as required.

## Final verdict

`FAIL_CLOSED_NO_LIVE_SOURCE_BYTES_AVAILABLE_FOR_FUNCTION_LEVEL_VERIFICATION`

Rationale: the shared-writer logic, rollback/compensation logic, file
staging/restoration logic, and stale-date sanitizer logic have all been
implemented and PASS a genuine (non-placeholder) sandbox test suite against
synthetic fixtures that reproduce the documented live defect shape
(UA-0009/0010/0011/0012 rows, mixed published states, protected vs.
ferry statuses, a stale arrival sentence containing `9 вересня 2026`).
However, the release candidate cannot be honestly reported as
`PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` yet, because the fail-closed
function-level anchor described in the contract (item 10: "fail closed on
both the full-file SHA above and the exact active function source/hash")
requires real captured function source for `konteyner.prinyat`,
`konteyner.sprosit_dni`, `konteyner._peresobrat`, `cars_ui.apply_value`, and
`cars_ui.toggle_publish`, which has not been supplied to this task. Until a
separate, evidence-backed Gate A step captures and records that real
function source (the same way the full-file SHA-256 anchors were captured in
TASK 076/077), `live_patcher.apply()` will keep failing closed, exactly as
designed, and this release candidate cannot claim readiness for production
approval.

Production touched: **NO**. CRM/site touched: **NO**.
