# TASK 048 report — restore candidate_transforms.py and close rebuild/launcher defects

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope

This task repairs exactly `candidate_transforms.py`. TASK 046's commit
5214cc5c9fb3005aab7321be6180eacb7b58e515 is rejected: an independent full
run reported 260 tests, 195 PASS / 12 FAIL / 53 ERROR, and the file itself
was disclosed by its author to be a clean-room 12 KB reconstruction that
deleted required public APIs. That file is **not** used as a baseline
anywhere in this delivery.

The delivered `candidate_transforms.py` starts from the embedded TASK 041
accepted baseline (as pasted verbatim in the task body) and applies only
the bounded, targeted corrections described in the task:

1. **Compatibility restored.** All required names are present with the
   original stable schema (`status`, `candidate`, `reasons`, `metadata`):
   `_ok`, `_blocked`, `CrossProcessLock`, `SingletonGuard`, `RebuildQueue`,
   `generate_runtime_support_source`, `transform_usercustomize`,
   `transform_launcher_singleton`, `transform_avtoperedacha_rebuild`,
   `transform_sqlite_short_ownership`,
   `check_db_closed_before_slow_work_candidate`, and all supporting
   constants/helpers used by the TASK 031/038/041 suites
   (`RUNTIME_SUPPORT_SOURCE`, `RUNTIME_MODULE_NAME`,
   `CANDIDATE_FORBIDDEN_USERCUSTOMIZE_MODULES`,
   `ALLOWED_HARMLESS_USERCUSTOMIZE_IMPORTS`, `SPAWN_*` sets, etc.).
   TASK 046's incompatible `code`/`reason` schema was never introduced.

2. **Parent-aware rebuild transform — one real defect closed.** The
   embedded baseline's `_Replacer` inside `transform_avtoperedacha_rebuild`
   only implemented `visit_Expr`. The task explicitly requires two
   supported trigger contexts: `Expr(Call) -> Expr(_queue.enqueue())` and
   exact `Return(Call) -> Return(_queue.enqueue())`. Without `visit_Return`,
   a legitimate `return gen()` / `return subprocess.run(...)` trigger would
   survive the rewrite pass unchanged and then be rejected by the
   post-transform "no direct calls / no spawn calls survive" proof for the
   wrong reason (looking like an unsupported context instead of being
   correctly rewritten). `visit_Return` was added, mirroring `visit_Expr`
   exactly, restricted to the same two trigger shapes (call to the proven
   generator, or a proven alias-resolved literal-matched spawn call for
   that generator).
   A second real gap was closed: the post-transform AST proof did not
   previously reject a rewritten trigger that happened to be a bare,
   unconditional **module-level** `Expr(_queue.enqueue())` statement, which
   would execute the queue at import time — contrary to "no module-level
   enqueue/callback execution". An explicit final check now walks only
   `post_tree.body` (module top level) and BLOCKs
   (`module_level_enqueue_execution_blocked`) if such a statement survived.
   All other call-graph proof logic (`_collect_spawn_aliases`,
   `_is_spawn_call_resolved`, `_spawn_matches_generator`,
   `_zero_arg_functions`, `_find_in_process_call_sites`,
   `_module_level_call_to`, the single-`_queue = RebuildQueue(fn, path)`
   insertion immediately after the generator definition, and every
   post-transform AST proof already present in the baseline) is preserved
   unchanged. TASK 038 positive and TASK 041 aliased-subprocess positive
   remain OK; unrelated spawn, no-direct-call, nonzero-arg, module-level
   direct call, assignment-context use, and ambiguous two-candidate cases
   remain BLOCKED (all exercised by the new test file).

3. **Launcher relocation implemented; generated runtime signal-cleanup
   defect closed.**
   - The embedded baseline's `transform_launcher_singleton` did **not**
     relocate any imports; it only validated pre-guard statements and
     wrapped the original main-guard body in the singleton
     install/try/finally scaffold, leaving all application imports at
     module scope. This did not meet the task's explicit relocation
     requirement. The rewritten transform now: keeps the docstring and
     leading `__future__` imports first; keeps only an explicit bounded
     stdlib allowlist (`ALLOWED_PRE_GUARD_STDLIB_IMPORTS`) plus the
     generated `SingletonGuard` import above the guard; moves every other
     statically resolvable `Import`/`ImportFrom` node into the single
     `if __name__ == "__main__":` guard, after `guard.install()` succeeds
     and before the original main actions, preserving module-global
     binding semantics (moved imports execute at module scope inside the
     guard body, so `global` binding is unchanged); BLOCKs on relative
     imports (`level > 0`), star imports, and any `__import__`/
     `importlib.import_module` dynamic-import call found anywhere in the
     module; BLOCKs when a moved alias is referenced by a decorator, class
     base/keyword, function/class default, or an annotation evaluated at
     definition time (checked against every kept pre-guard
     function/class definition) — ordinary function-body references are
     left alone since they resolve when the function is later called.
     The duplicate-start diagnostic + `SystemExit(78)` still executes
     before any moved import, and `finally: guard.cleanup()` is preserved.
     Module-import-only execution (no `__main__`) still neither acquires
     the lock nor imports any moved application module, and the main path
     is proven (by the new tests) to call `guard.install()` before any
     moved application module is imported or used.
   - The generated `RUNTIME_SUPPORT_SOURCE`'s `SingletonGuard.install()`
     recorded the previous SIGINT/SIGTERM handler locally per-closure but
     `cleanup()` only called `self.release()` — it never restored any
     signal handler, so repeated installs would stack unrelated wrapper
     handlers and the original handlers were permanently lost. This is now
     fixed: `SingletonGuard.__init__` tracks `_installed_handlers`;
     `install()` records `{signal_number: previous_handler}` for every
     handler it actually changes; `cleanup()` restores each recorded
     handler via `signal.signal(sig, previous)`, then clears the tracking
     dict, then releases the lock — so a second `cleanup()` call is a
     documented no-op for the handler-restore step (idempotent) and never
     raises. The generated per-signal wrapper now calls `_self.cleanup()`
     (full restore + release) before delegating to a callable previous
     handler, instead of only `_self.release()`. All other runtime
     behavior (`CrossProcessLock` liveness/staleness proof, atexit
     registration, `RebuildQueue` coalescing/ack/error-sanitization, and
     deterministic source text) is byte-for-byte unchanged from the
     accepted TASK 041 baseline.

4. **Tests.** `test_task_048_candidate_restore.py` is a new, compact,
   focused suite (not a copy of any older suite). It exercises: presence
   of every compatibility name and the stable result schema; Expr and
   Return rebuild positives plus an aliased-spawn positive; six rebuild
   negatives (unrelated spawn, no direct call, nonzero-arg generator,
   module-level direct call, assignment-context use, ambiguous two full
   candidates); launcher future-import compilation; module-import-only
   execution importing neither the fake runtime lock nor the fake
   application module; main-path ordering proof (`install` before
   `app_ran`); duplicate-start `SystemExit(78)` proof before any
   application import; definition-time moved-alias decorator ambiguity
   BLOCK; relative-import BLOCK; and generated-runtime signal-handler
   cleanup idempotency using monkeypatched fake handlers (no real signal
   delivery, no real process interaction beyond a temporary-directory
   file lock).

## What was verified locally

- `python3 -m py_compile candidate_transforms.py
  test_task_048_candidate_restore.py` — both compile.
- `python3 -m unittest test_task_048_candidate_restore -v` was executed
  against this file locally in the sandbox that authored it; all cases in
  this new file passed. `sqlite_ownership.py` (an unchanged file from an
  earlier task, not redelivered here) was present in the same directory
  for that run, since `candidate_transforms.py` imports it at module
  level (unchanged from the TASK 041 baseline).

## What is explicitly NOT claimed

- The full CRM-SPEED-001 package is **not** claimed green. TASK 046's
  `sqlite_ownership.py` state and the orchestrator/controller closure
  remain pending and are out of scope for this task; they will be
  restored/verified separately.
- No Gate A execution occurred. No PythonAnywhere access occurred. No
  Production or CRM file was read, written, or reloaded.
- No claim is made that this file, once merged, has been independently
  re-run by the controller across the full historical suite; that
  independent audit is the next required step.

## Status

PARTIAL_TASK_048_CANDIDATE_RESTORED_READY_FOR_CONTROLLER_AUDIT

This is explicitly **not** READY_FOR_GATE_A. SQLite-ownership file state
and full orchestrator closure remain pending and unverified by this task.

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
