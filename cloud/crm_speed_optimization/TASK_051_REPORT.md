# TASK 051 — CRM-SPEED-001 restore SQLite ownership from exact baseline

OWNER_DIRECTIVE_MARKERS (do not alter):
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope

Work performed only under `cloud/crm_speed_optimization/`. No file outside
`cloud/` was read or written. No Production, CRM, database, bot, site,
generators, WSGI, scheduled tasks, or `tasks/` paths were touched. No
network access, no installs, no Gate A execution, no UA-0009 publication.

## What was restored

TASK 046's clean-room `sqlite_ownership.py` deleted the accepted Section 2
evidence API (`OwnershipEvidence`, `collect_ua0009_ownership_evidence`,
`compare_ownership_evidence`) and caused 53 test errors. This task restores
the module starting from the exact TASK 041 baseline text embedded in the
task (matching the declared baseline commit `65e1b53e...`), keeping Section
2 byte-for-byte identical to the accepted baseline.

## What was changed (Section 1 only, before the canonical evidence API)

The baseline TASK 041 transform/verifier already provided:
- `AnchorNotFoundError`, `find_db_handle_names`, `verify_no_live_handle_across_slow_call`,
  `transform_short_ownership` with single-connection / at-most-one-cursor discovery via
  `conn.cursor()`, straight-line-only ownership segments, write-SQL/commit/rollback
  rejection, literal-SQL requirement, fetch materialization, and per-name independent
  open/closed tracking in the verifier (so an unrelated `.close()` cannot suppress a
  violation).

TASK 051 adds the following corrections on top of that baseline, per the task's
detailed Sections 2–4, while preserving every public name/signature/return type:

1. `find_cursor_names` now also recognizes `cur = conn.execute(literal_sql, ...)` as a
   valid cursor-owning assignment, in addition to `cur = conn.cursor()`.
2. A new `_detect_escape` helper rejects: `return` of a tracked handle, aliasing
   (`other = cur`), storing a tracked handle into an attribute/subscript target, passing
   a tracked handle as a positional or keyword argument to any call other than its own
   `cursor`/`execute`/`executemany`/`fetch*`/`close` methods, and closure capture by a
   nested function/lambda referencing the tracked names.
3. `_ensure_short_timeout` now normalizes an *existing* `timeout=` keyword to exactly
   `timeout=2` instead of only adding it when absent, guaranteeing exactly one
   `timeout=2` keyword on the local connect call while preserving every other
   positional/keyword argument.
4. `transform_short_ownership` now:
   - removes the function's own original `close()` statements on tracked names from the
     ownership segment (via `_is_close_stmt_on_names`) so the generated `finally` never
     double-closes and never leaves a close after the ownership block;
   - materializes `fetchall()`/`fetchmany()` results as
     `tuple(tuple(row) for row in <name>)` (tuple-of-tuples) rather than a single-level
     `tuple()`, immediately after the fetch call and before any close;
   - emits `conn = None` (and `cur = None` when a cursor is tracked) before the
     generated `try`, so `finally` guards (`if <name> is not None: <name>.close()`)
     can never raise `UnboundLocalError` on a connect/execute/fetch failure, and the
     original exception type/message always propagates unmodified;
   - closes the cursor first, then the connection, in `finally`, each guarded and each
     exactly once.
5. `verify_no_live_handle_across_slow_call` and Section 2 (the canonical UA-0009
   evidence API) are unchanged from the accepted baseline text.

## Tests added

`test_task_051_sqlite_restore.py` (new, compact, no legacy-suite copying) uses only fake
in-process sqlite-like objects and one throwaway temp-file SQLite database. It covers:
 cursor discovery via both `.cursor()` and `.execute()`; rejection of `return cur`,
aliasing/escape, caller-owned handles, multiple connections, branching, write SQL, and
non-literal SQL; exactly-once `timeout=2` normalization with original args/kwargs
preserved; tuple-of-tuples materialization; cursor-before-connection close ordering
exactly once each; success, connect-failure, execute-failure, and fetch-failure paths
with original exception type/message preserved (no `UnboundLocalError`); verifier
behavior showing an unrelated `.close()` cannot suppress a real violation; presence of
all baseline evidence-API public names; and a minimal in-memory/temp-file legacy
evidence-API round trip (`collect_ua0009_ownership_evidence` /
`compare_ownership_evidence` / missing-row `BLOCKED` path) confirming no raw field
values leak into the evidence dict. It also compiles every `.py` file in the package
directory.

## What was NOT executed by this task

As an authoring task, this deliverable does not itself run `pytest` against a live
interpreter, and it does not run the original TASK 034/038/041 legacy test files
(those files were not provided in this task's context and are excluded from the
deliverable list per instructions: "do not copy legacy suites"). The controller is
expected to execute `python -m pytest` for both the new file and any restored legacy
TASK 034/038/041 suites still present on `main`, and to compile all package `.py`
files, as part of independent audit. No claim is made here that any execution,
upload, or visual check has occurred.

## Status

PARTIAL_TASK_051_SQLITE_RESTORED_READY_FOR_CONTROLLER_AUDIT

This is explicitly **not** READY_FOR_GATE_A. The launcher class-body edge case and the
orchestrator receipt-closure work remain pending and are out of scope for this task.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
