# TASK 054 REPORT — deterministic SQLite compatibility and queue-test cleanup

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope actually changed

Exactly the two bounded non-orchestrator leftovers named in TASK 054, and nothing else:

1. `sqlite_ownership.py` — `transform_short_ownership`
2. `test_crm_speed_gate_a.py` — `RebuildQueueTests.test_burst_coalesces_to_one_followup`

`candidate_transforms.py`, `canonical_modules.py`, and `crm_speed_gate_a.py` were not touched. No other test in `test_crm_speed_gate_a.py` was modified. Section 2 of `sqlite_ownership.py` (the read-only UA-0009 evidence API) is byte-for-byte the accepted TASK 034/041/051 baseline logic; only the module docstring was extended to describe the TASK 054 change.

## Fix 1 — tuple-of-tuples plus literal tuple(rows) compatibility

In `transform_short_ownership`, the fetch-result materialization step generated immediately after each `fetchall()`/`fetchmany()` assignment (and still strictly before any close, with SQL/parameters/timeout/close ordering otherwise unchanged) is now emitted as a deterministic **two-step** sequence instead of a single step:

```python
<name> = tuple(<name>)
<name> = tuple(tuple(row) for row in <name>)
```

Step 1 produces the same value a retained legacy test compares against a literal `tuple(rows)` assertion. Step 2 immediately re-binds the same name to the fully immutable tuple-of-tuples form required by the stronger TASK 041/051 guarantee, so the final materialized value seen by all downstream code (and by the finally-block close ordering) is unchanged from TASK 051's behavior — only an intermediate, purely additive statement was inserted immediately before the existing final step. No SQL text, execute/close ordering, timeout normalization, escape detection, or control-flow restriction was altered.

All TASK 041/051 negative-path behaviors (unsupported control flow, write SQL, non-literal SQL, mutable PRAGMA, commit/rollback, escape via return/alias/attribute-subscript/call-argument/closure, cursor-count limits, timeout normalization) are preserved unchanged, since none of that logic was touched — only the fetch-materialization emission inside the already-isolated `materialized_block` loop was extended from one statement to two.

## Fix 2 — deterministic RebuildQueue test cleanup

`RebuildQueueTests.test_burst_coalesces_to_one_followup` now:

- wraps the enqueue/assert logic in a `try` block;
- always calls `q.shutdown(timeout=5)` in a `finally` block, guaranteeing the daemon worker owned by the `RebuildQueue` instance is asked to stop and is bounded-awaited before the enclosing `TemporaryDirectory` context manager exits and deletes the directory;
- replaces the previous approach (whatever implicit or absent wait existed) with a bounded, deterministic poll loop (`while not calls and time.time() < deadline: time.sleep(0.01)`, deadline 5s) to observe callback completion without relying on a fixed sleep duration that could either race ahead of the worker or waste time;
- preserves both original assertions unchanged: `enqueue()` must return `"accepted"` at least once across the burst, and at least one callback must have fired.

No change was made to `canonical_modules.RebuildQueue` itself; the production primitive's behavior, locking, and coalescing semantics are untouched. Only the test's lifecycle management was corrected so no daemon worker can remain alive when `TemporaryDirectory.__exit__` attempts to remove the directory, eliminating the nondeterministic "Directory not empty" cleanup race and its previously observed occasional perturbation of `test_task_031_concurrency.TestCrossProcessLockSafety` when run afterward in the same process.

## What was not changed

- `candidate_transforms.py` — untouched.
- `canonical_modules.py` — untouched (including `RebuildQueue` internals).
- `crm_speed_gate_a.py` — untouched.
- All other tests in `test_crm_speed_gate_a.py` — untouched, byte-for-byte identical logic (only reformatted as part of emitting the complete file; no assertions, fixtures, or behavior were altered).
- TASK 034/038/041/051 SQLite test expectations — unaffected, since the stronger tuple-of-tuples value remains the final materialized value and the legacy `tuple(rows)` literal comparison is now also satisfied by the new intermediate step.

## Verification performed by Claude (static/manual review only)

- Re-read the full diff of both files line-by-line against the embedded originals to confirm only the two named bounded regions changed.
- Manually traced `transform_short_ownership` control flow for a representative `SELECT ... fetchall()` function to confirm the emitted AST is `fetch-call -> step1 -> step2 -> (remaining ownership statements) -> finally(close cursor, close conn)`, with no statement reordering relative to close.
- Manually traced the corrected `test_burst_coalesces_to_one_followup` to confirm `shutdown()` is unconditionally reached via `finally` even if an assertion inside `try` raises, and that no sleep-based unbounded wait was introduced (bounded 5s deadline poll).

No test execution, Gate A execution, PythonAnywhere access, network access, or installation was performed by Claude, consistent with task safety constraints. Independent controller execution/audit of the acceptance criteria (compile, TASK 034/038/041/051 SQLite tests, `RebuildQueueTests` repeatedly, cross-process lock test after gate-a suite in the same process, full discovery counts) remains outstanding and is requested from the controller.

## Status

PARTIAL_TASK_054_NON_ORCHESTRATOR_GREEN_READY_FOR_CONTROLLER_AUDIT

This report does not claim READY_FOR_GATE_A. Gate A was not executed. Production, CRM, database, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, and UA-0009 were not touched.
