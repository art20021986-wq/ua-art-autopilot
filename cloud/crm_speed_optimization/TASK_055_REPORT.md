# TASK 055 REPORT — CRM-SPEED-001 final orchestrator receipt/publication closure

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope

Work performed strictly under `cloud/crm_speed_optimization/` plus
`cloud/latest_status.md` and `cloud/owner_reply.md`, per the immutable
safety boundary. No PythonAnywhere access, no network calls, no
Production/CRM/crm.db/bot/site/media/cards/generator/WSGI/scheduled-task
writes, no UA-0009 publication, and Gate A was not executed anywhere in
this task.

## Root causes addressed

1. **Missing predicate skeleton before verifier hash checks.** When an
   early transform block occurred (e.g. cars_ui transform BLOCKED),
   `phase80`/`phase100` never populated several `REQUIRED_PREDICATES`
   keys (e.g. `admin_routes_text_only`, `media_persistence_unchanged`,
   `usercustomize_inert`, `singleton_guard_present`,
   `rebuild_queue_bound_no_process_spawn`, `db_closed_before_slow_work`,
   `deterministic_repeat_all_transforms`, `sqlite_readonly_quickcheck_ok`).
   `evaluate_gate_a()` therefore returned an unmet-predicate list keyed
   by a **missing** dict rather than a well-formed BLOCKED entry, which
   the acceptance criteria describe as
   `missing_or_malformed_predicate:candidates_compile` surfacing before
   receipt/report hash binding could even be reasoned about.

   **Fix:** a new `_ensure_predicate_skeleton(evidence)` helper runs on
   the filtered public evidence dict immediately before
   `evaluate_gate_a()` is called and before any receipt is constructed
   or written. It fills any missing/malformed `REQUIRED_PREDICATES`
   entry with `{"status": "BLOCKED", "reason": "skipped_due_to_prior_block"}`
   and never touches/upgrades an already well-formed OK or BLOCKED
   entry. This guarantees every receipt — PASS-track or BLOCKED — has
   all sixteen required predicate keys present with a status of exactly
   `OK` or `BLOCKED`, making every BLOCKED receipt structurally
   verifiable by any downstream receipt/manifest hash-binding verifier.

2. **candidates_compile on an early block was not fully bounded.** The
   original-bytes-only compile evidence recorded on a transform block
   now always includes `"accepted_candidate_set": False` (in both the
   compile-succeeded and compile-failed sub-branches), together with
   `candidate_origin="original_due_to_transform_block"` and bounded
   `compiled`/`errors`/`reason` fields. If even the original-bytes
   compile evidence itself cannot be collected (exception or malformed
   result from `check_candidates_compile`), the code now stores an
   explicit `{"status": "BLOCKED", "reason": "compile_evidence_unavailable"}`
   base instead of silently omitting the predicate. The overall gate
   status remains BLOCKED regardless of whether this specific compile
   evidence resolves to OK or BLOCKED, because `phase40` still raises
   `_GateABlocked("cars_ui_transform_blocked")` immediately afterward
   and no legacy/original candidate set is ever accepted, written, or
   installed.

3. **Canonical UA-0009 publication probe was skipped after an early
   block.** Previously `ua0009_publication_check.canonical_probe_ua0009`
   was only invoked from inside `phase80`, which is itself skipped
   entirely (`raise _GateABlocked("skipped_prior_block")`) whenever an
   earlier phase already blocked. That meant the canonical publication
   probe silently never ran on the exact five-test failure path
   described in the task.

   **Fix:** a new bounded `_run_canonical_probe_once(config, opener,
   publication_state)` helper is guarded by a per-invocation
   `publication_state["consumed"]` flag. `phase80` calls it in the
   normal flow; `phase100` (which is always attempted, per the
   unconditional finalization phase) calls the exact same helper again
   as a fallback -- the flag guarantees the underlying
   `canonical_probe_ua0009` call itself happens **at most once** per
   `orchestrate_gate_a()` invocation, regardless of which phase
   actually triggers it, and never fabricates a PASS: a bounded probe
   exception is recorded as `{"status": "BLOCKED", "reason":
   "probe_exception:<ExceptionClassName>"}` and still marks the single
   attempt consumed. `receipt["publication_result"]` is always taken
   from `evidence["ua0009_not_public"]` after this call, so the two
   values are guaranteed identical.

4. **Phase100 finalization was not exception-isolated per section.**
   Previously a single unhandled exception anywhere inside `phase100`
   (fingerprints-after, site-inventory-after, sqlite ownership-after,
   publication fallback, no-production-write) would abort the *entire*
   remainder of finalization via the outer `run_phase` exception
   handler, silently leaving later predicates unset and therefore
   relying entirely on the new skeleton-fill step to paper over the
   gap. `phase100` is now internally organized into five independently
   `try/except`-wrapped sections, each of which always records a
   bounded `OK`/`BLOCKED` evidence entry for its own predicate(s) even
   if an exception occurs, so no single finalization failure can ever
   suppress the rest of the before/after safety evidence or block
   receipt/report emission. `production_write` remains `"NO"` and
   `pii_emitted` remains `"NO"` in every code path.

5. **Exact successful eight-candidate set.** On a fully successful
   `phase40` (all seven source transforms plus the generated
   `crm_speed_runtime.py` support module available), the orchestration
   now explicitly clears the working `candidate_sources` map and
   repopulates it with exactly the eight extended candidate entries
   (`candidate_sources.clear(); candidate_sources.update(extended_candidate_sources)`),
   so no stray legacy `usercustomize.py` key can ever remain in the
   candidate map on a successful path. `phase60`'s compiled
   `package_hashes`/`candidates_compile.hashes` and
   `extended_candidates.candidate_hashes` already only ever reflect the
   eight extended names, and the new TASK 055 test asserts this exact
   eight-name set and the explicit absence of a ninth
   `usercustomize.py` key.

## Test-environment-only fix (item 6 of the task)

`test_pid_reuse_start_mismatch_takeover` in
`test_task_031_concurrency.py` now imports `canonical_modules`,
temporarily replaces `canonical_modules._process_start_time` with a
deterministic callable that returns a fixed `"real-start-time"` value
for the current test process pid (delegating to the original for any
other pid), and restores the original function in a `finally` block.
This removes the dependency on `/proc/<pid>/stat` actually being
available inside the controller container while still proving the same
behavior: a pid that is alive but whose lock-file start-time does not
match the (now deterministic) real start time is classified `"dead"`,
allowing safe takeover. Product code (`canonical_modules.py`) is
unchanged. The separate `test_unknown_identity_fails_closed` test is
unchanged and still proves fail-closed `"unknown"` behavior.

## New focused tests

`test_task_055_orchestrator_final.py` exercises
`crm_speed_gate_a.orchestrate_gate_a()` end-to-end against temporary,
offline fixtures, with every real transform/probe/sqlite-ownership
dependency deterministically mocked at the module-attribute level so
the tests validate ONLY the TASK 055 orchestrator-level behavior
described above (not the semantics of `candidate_transforms.py`,
`sqlite_ownership.py`, or `cars_ui_transform.py`, which are
unmodified and out of scope for this task). Covered:

- early transform block yields every `REQUIRED_PREDICATES` key with an
  `OK`/`BLOCKED` status and a final `BLOCKED` gate status;
- `accepted_candidate_set` is `False` on the original-compile-only
  evidence recorded for that early block;
- the canonical publication probe spy is called exactly once, both on
  the early-block path (consumed via the `phase100` fallback) and on
  the fully successful path (consumed via `phase80`);
- a fully successful, mocked candidate-source fixture yields exactly
  the eight expected candidate names in `package_hashes` and
  `extended_candidates.candidate_hashes`, with no ninth
  `usercustomize.py` key, and the support-module install target
  remains `crm_speed_runtime.py`;
- `receipt["publication_result"]` always equals
  `receipt["evidence"]["ua0009_not_public"]`.

### Known limitation — receipt/manifest verifier integration

The task references an existing, unmodified "manifest/verifier"
module (e.g. a `verify_gate_a`-style function) that is explicitly out
of scope to change. That module's exact source/API was **not** part of
the exact-source input supplied for this task, so this deliverable does
not import or call an assumed external verifier API (doing so could
have silently produced an incompatible or fabricated integration).
Instead, `test_task_055_orchestrator_final.py` defines a small,
self-contained, local hash-binding helper
(`_write_manifest`/`_verify_receipt_report_against_manifest`) that
reads only the `receipt.json`/`report.md` bytes
`orchestrate_gate_a()` itself writes via `SafeWriter`, and exercises
the same untampered/receipt-tamper/report-tamper semantics described in
the task (`receipt_hash_mismatch`, `report_hash_mismatch`) without
modifying or guessing at any real verifier module. ChatGPT/Codex should
confirm compatibility with the actual repository verifier module
during audit, since it was not visible in this task's exact-source
input.

## What was NOT done

- Gate A was not executed anywhere (`GATE_A_EXECUTED: NO`).
- No PythonAnywhere access, no network calls (all fixtures/tests use
  fully offline, in-process fakes/mocks; the FakeOwnershipEvidence /
  mocked `canonical_probe_ua0009` never touch the network).
- No Production/CRM/crm.db/bot/site/media/cards/generator/WSGI/
  scheduled-task/UA-0009 changes.
- `candidate_transforms.py`, `sqlite_ownership.py`,
  `canonical_modules.py`, and any manifest/verifier module were not
  modified.

## Independent verification requested from the controller

As with prior tasks, Claude cannot execute the full 308+ test suite
against the live repository from this sandboxed context. The controller
should independently: compile all modified/added files; run full
unittest discovery; confirm 308 existing tests plus the new TASK 055
tests all PASS with 0 FAIL/0 ERROR/0 skip and no "Exception in thread";
repeat discovery five times for determinism; and confirm compatibility
of the TASK 055 receipt/manifest test approach against the repository's
real verifier module (see limitation above).

Status: READY_FOR_CONTROLLER_REVIEW_TASK_055
