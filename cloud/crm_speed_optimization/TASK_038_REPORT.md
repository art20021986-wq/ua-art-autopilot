# TASK 038 REPORT — CRM-SPEED-001 real candidate transforms and RebuildQueue cleanup

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Scope

This round addresses the two independent controller-identified defects
from the audit of commit `ad4a7d8aa01eb4c5901b49d7a74ce10af5f19a01`.

### Defect A — escaped background-thread exception (FIXED)

`canonical_modules.RebuildQueue._loop` now constructs and acquires the
`CrossProcessLock` **inside** the same exception boundary that guards
callback invocation, release, and worker-state cleanup. If the lock
parent directory disappears (or lock construction/acquisition fails for
any other reason):

- the pending acknowledgement event is still set immediately (so
  `enqueue()` never blocks past its bounded timeout),
- exactly one bounded, sanitized error (`type(exc).__name__` only — no
  paths, no PII) is appended to `errors`,
- `running`/`pending` state is cleared under the condition lock and
  waiters are notified,
- the worker iteration terminates without retry or spin,
- no exception can reach `threading.excepthook`.

A deterministic regression
(`test_task_038_real_candidates.RebuildQueueNoEscapeTests.
test_deleted_lock_parent_no_escaped_exception`) installs a
`threading.excepthook` spy, deletes the lock parent before
construction, and asserts zero excepthook calls, zero callback
invocations, exactly one recorded error, a clean idle/stopped queue,
and no directory recreation. All pre-existing RebuildQueue tests
(burst coalescing, slow-callback prompt return, bounded callback-error
handling, the 100-round multiprocess lock stress test) are preserved
unmodified and continue to pass against the corrected implementation,
since their behavior only changed in the previously-unreachable failure
path.

The same corrected `_loop` logic is also embedded, verbatim in spirit,
inside the generated `crm_speed_runtime.py` support candidate (see
below), so any launcher/rebuild candidate that imports it inherits the
same no-escape guarantee.

### Defect B — phase40 only transformed cars_ui.py (ADDRESSED)

`candidate_transforms.py` is a new, single, canonical, fail-closed,
AST-only transform module (never imports/executes application source;
regex is never used for broad rewriting) providing:

- `transform_usercustomize(source, version)` — removes known forbidden
  application/background imports (`team_bot`, `run_all`, `start_safe`,
  `avtoperedacha`, `stranica`, `threading`, `multiprocessing`,
  `subprocess`) while preserving docstring/`__future__`/literal
  assignments/inert definitions; any unclassified top-level statement
  BLOCKS. Used independently for both the Python 3.10 and Python 3.13
  `usercustomize.py` inputs, producing two distinct candidates
  (`usercustomize_py310.py`, `usercustomize_py313.py`).
- `transform_launcher_singleton(source, lock_path)` — requires exactly
  one `if __name__ == "__main__":` anchor and no import-time side
  effects outside imports/defs/literal assignments; wraps that exact
  entry in a `SingletonGuard(...).install()/cleanup()` try/finally using
  the shared deterministic lock path. Used for both `start_safe.py` and
  `run_all.py`, so starting through either cannot create duplicate
  runtimes.
- `generate_runtime_support_source()` — deterministic, standard-library
  only `crm_speed_runtime.py` candidate containing the minimal canonical
  `CrossProcessLock`, `SingletonGuard`, and the corrected
  no-escaped-exception `RebuildQueue`. Never acquires a lock, starts a
  thread, or performs I/O when generated. Treated as the eighth
  candidate: compiled, hashed, written, and included in the receipt.
- `transform_avtoperedacha_rebuild(source)` — structurally identifies
  exactly one in-process generator function (by name-hint anchor,
  e.g. containing `stranica`), binds it to one module-level
  `RebuildQueue` from `crm_speed_runtime`, and replaces every
  structurally-detected `subprocess.Popen/system/call/run/check_call/
  check_output` rebuild call site with `_queue.enqueue()`. Removes the
  now-unused `subprocess` import when no reachable use remains. Two or
  more generator candidates, or no reachable spawn site, BLOCK. The
  generator is never executed during transform.
- `transform_sqlite_short_ownership(source, function_names=None)` —
  delegates directly to the existing canonical
  `sqlite_ownership.transform_short_ownership` (no second divergent
  transformer created), auto-discovering DB-handle functions via
  `sqlite_ownership.find_db_handle_names` when `function_names` is not
  supplied. Used for both `avtoperedacha.py` and `samokontrol.py`.
- `check_db_closed_before_slow_work_candidate(source)` — verifies a
  **candidate** string with the canonical, handle-specific
  `sqlite_ownership.verify_no_live_handle_across_slow_call`.

`crm_speed_gate_a.py` phase40/60/80 were extended (not duplicated) to:

- resolve two distinct `usercustomize.py` paths by their
  `python3.10`/`python3.13` parent components
  (`_resolve_two_usercustomize_paths`), and one each of `start_safe.py`,
  `run_all.py`, `samokontrol.py` (`_resolve_unique_input`); missing or
  ambiguous mapping is recorded as an extended-generation block reason
  rather than silently choosing the first match;
- when all seven real sources resolve unambiguously, transform all
  seven plus generate the support module, write every candidate and
  unified diff through `SafeWriter` under `candidates/`/`diffs/` in the
  isolated run directory, and compile all eight together without
  importing any of them;
- evaluate `usercustomize_inert`, `singleton_guard_present`,
  `rebuild_queue_bound_no_process_spawn`, `db_closed_before_slow_work`,
  and `deterministic_repeat_all_transforms` against the **generated
  candidates**, not the originals (verified by a dedicated spy test);
- record per-candidate original/candidate/diff hashes, transform
  status/reasons/metadata, compilation status, deterministic repeat
  records (10x per transform, including the support module), and the
  support-module install target in the receipt under
  `extended_candidates`.

### Backward compatibility

When a config does not resolve the full seven-source, two-version
usercustomize set (as in the pre-TASK-038 fixtures used by
`test_task_032_orchestration.py` and `test_task_035_integration.py`,
which were not modified), extended generation is reported unavailable
and the historical single-cars_ui/legacy-usercustomize evidence path is
preserved byte-for-byte, so no pre-existing test was weakened, skipped,
or rewritten.

## Honest scope limitations

- The avtoperedacha generator-anchor detection uses a conservative
  name-hint heuristic (`stranica`/`generate_page`/`render_page`/
  `build_page`) rather than a full call-graph resolution across
  arbitrarily-shaped production sources; on real production sources
  this heuristic should be reviewed against the exact `avtoperedacha.py`
  shape before Gate A execution.
- `sqlite_ownership.py` was reused unchanged (not further tightened)
  given the scope of this round; it already enforces try/finally
  closure guarantees and short timeouts, and
  `check_db_closed_before_slow_work_candidate` independently verifies
  ordering on the resulting candidate, so a badly-ordered original
  cannot silently produce a passing predicate.
- `singleton_guard_present` for the extended path combines a static
  substring check (candidate references `SingletonGuard`,
  `crm_speed_runtime`, and the shared lock path) with the existing
  canonical behavioral `check_singleton_guard_present` test; it does not
  execute the generated launcher candidates (Gate A must never do so).
- The 15 mandatory regressions in the task text are covered
  substantially but not exhaustively by
  `test_task_038_real_candidates.py`; item 15 ("existing full discovery
  remains green") is asserted indirectly via preserved/unmodified
  existing test files plus a compile-sanity test, not by re-running the
  full 188-test suite from within this report.

## Verdict requested

This package is submitted for independent controller review. It is
**not** a claim of Gate A execution, production acceleration, CRM
change, or UA-0009 publication readiness.
