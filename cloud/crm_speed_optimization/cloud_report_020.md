# CLOUD REPORT — CRM-SPEED-001 (TASK 026, controller rejection round 3)

## Scope of this round

This round responds to the controller's executed result for commit
73ac2b4744e27172a7011967f70e47df4ba86ca8: 56/59 tests passing on the first
run, with 3 named failures, and required corrections A-E from TASK 026.

## What changed

1. **Dynamic dispatch (correction A).** `scan_reachable_call_graph` in
   `crm_speed_gate_a.py` now performs a bounded reachable call-graph walk
   from the four admin routes and unconditionally records
   `getattr/setattr/eval/exec/globals/locals` calls, bound-method aliases,
   callback dict/list entries holding a media-bound attribute, return
   aliases, chained calls, and subscript dispatch as violations.
   `transform_cars_ui` refuses to return a modified-but-unsafe candidate:
   if any violation other than a plain `direct_media_call` is present in
   the *original* graph, the candidate is `None` and status is `BLOCKED`.
   Only when the original graph contains solely direct, non-dynamic media
   calls does the transformer rewrite those call sites to text and
   re-scan the result, requiring the re-scan to be clean.

2. **Deterministic repeat API (correction B).** The function signature is
   now exactly `measure_deterministic_repeat(transform_fn, source,
   args=(), repeats=10)`. It compares candidate SHA-256, unified-diff
   SHA-256, status, reasons, and a metadata digest across all repetitions.
   Five deliberately nondeterministic transform variants (random content,
   wall-clock time, UUID, unordered-set serialization, changing metadata)
   are exercised and proven to break determinism, and are shown forcing
   `evaluate_gate_a` to `BLOCKED` when substituted as evidence.

3. **Site inventory overflow (correction C).** `scan_bounded_inventory`
   gained an explicit `max_files_per_root` parameter defaulting to the
   unchanged production value `DEFAULT_MAX_FILES_PER_ROOT = 32`. Tests
   construct a real 3-matched-file case with `max_files_per_root=2` to
   force a genuine overflow, plus exact boundary N/N+1 tests. The
   production default cap was not lowered.

4. **Consolidation (correction D).** `canonical_modules.py` is now the
   single implementation of `CrossProcessLock`, `SingletonGuard`,
   `RebuildQueue`, and `SafeWriter`. `cross_process_lock.py`,
   `rebuild_queue.py`, and `safe_writer.py` are thin re-exports with no
   logic. `crm_speed_gate_a.py` imports these classes rather than
   redefining them. `IdentityTests` assert object identity across all
   four import paths.

5. **End-to-end truth (correction E).** `run_gate_a(fixture)` is a single
   public orchestration function. `EndToEndGateATests` builds one full
   synthetic fixture (bounded inputs, sqlite db with `PRAGMA quick_check`
   `ok`, backup archive with verified hash, site root, mocked HTTPS 404
   UA-0009 probe, clean cars_ui/usercustomize/avtoperedacha sources, and a
   DB-close-before-slow-work anchored function) and calls `run_gate_a`
   once, reaching `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` with an empty
   `unmet_predicates` list and a written `receipt.json`. Eleven further
   tests each mutate exactly one input and assert the matching predicate
   fails closed and the overall status becomes `BLOCKED`. No predicate in
   `evaluate_gate_a` can be `True` without a fresh evidence dict with
   `status == "OK"` produced by the corresponding check function.

## Honest limitations

- Claude/Cloud does not execute this suite itself as a substitute for
  controller verification; the exact 10-consecutive-green-run log for
  this round must come from the controller, as in prior rounds.
- The `CrossProcessLock` stress test uses 25 rounds x 4 independent
  processes (100 aggregate contention attempts) rather than a single
  100-iteration loop; documented in `TEST_MATRIX.md`.
- `check_db_closed_before_slow_work` is a bounded statement-order AST
  heuristic over an explicitly supplied anchored function source; it has
  not been run against the real `avtoperedacha.py`/`samokontrol.py`
  because those real sources are not available inside `cloud/`.
- `transform_cars_ui` has only been exercised against synthetic fixture
  sources in this delivery, per the authority boundary (no real source
  fetch/execution from `cloud/`).

## Status

READY_FOR_CONTROLLER_REVIEW. Not READY_FOR_GATE_A_EXECUTION. Not
deployed. Not installed.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

MEMORY_VERSION_READ: 4
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
