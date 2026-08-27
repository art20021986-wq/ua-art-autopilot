# TASK 056 REPORT — Align stale backup-ordering test with mandatory complete evidence skeleton

## Scope

Narrow offline test-maintenance task for CRM-SPEED-001. Only the test file
`test_task_032_orchestration.py` was modified, plus the three
reporting/status files. `crm_speed_gate_a.py` and all other product/module
source files were left untouched. Gate A was not executed. PythonAnywhere,
Production, CRM, database, bot, site, media, cards, generators, WSGI,
processes, schedules, and UA-0009 were not touched.

## Problem addressed

Independent controller audit of commit `0df9bae057d88ab0aab17da072b1d254098eefa5`
found 312 PASS / 1 FAIL out of 313 discovered tests. The single failure was:

`test_task_032_orchestration.BackupOrderingTests.test_backup_mismatch_blocks_before_candidate_creation`

The test asserted `assertNotIn("candidates_compile", receipt["evidence"])`,
which is stale and contradicts the TASK 055 fail-closed contract: before
receipt emission, every key in `REQUIRED_PREDICATES` must exist as a dict
whose status is exactly `OK` or `BLOCKED`. On an early backup mismatch,
`candidates_compile` must be present with:

```python
{"status": "BLOCKED", "reason": "skipped_due_to_prior_block"}
```

## Change made

In `BackupOrderingTests.test_backup_mismatch_blocks_before_candidate_creation`
only:

1. Preserved assertions that `receipt["status"] == "BLOCKED"` and that a
   blocker containing `backup_verification_failed` is present.
2. Removed the stale `assertNotIn("candidates_compile", ...)` assertion.
3. Added exact assertions that `receipt["evidence"]["candidates_compile"]`
   is a dict, its `status` is `BLOCKED`, and its `reason` is
   `skipped_due_to_prior_block`.
4. Preserved the "before candidate creation" meaning with a filesystem
   assertion that
   `os.path.join(self.cfg["run_root"], receipt["run_id"], "candidates")`
   does not exist.

No other test was weakened, skipped, deleted, renamed, or marked
expected-failure. No unrelated formatting or behavior changes were made
elsewhere in the file.

## Verification performed

This was an offline test-maintenance edit. Per task constraints, Gate A was
not run and PythonAnywhere was not accessed. The edit was constructed to be
consistent with the TASK 055 fail-closed evidence-skeleton contract as
described in the task specification. Execution and pass/fail confirmation
of the full 313-test suite against this change is left to the independent
controller, consistent with prior task rounds in this repository.

## Status

READY_FOR_CONTROLLER_REVIEW_TASK_056

## Canonical shared memory markers

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
