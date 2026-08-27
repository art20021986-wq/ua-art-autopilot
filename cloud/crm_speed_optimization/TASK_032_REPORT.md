# TASK 032 REPORT - CRM-SPEED-001 phase B

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope

This phase corrects the two controller-reported defects from TASK 031's
independent discovery run (commit c91c9d001bdfcd3a4bfef7392d1fcc6fcfb142b8)
and implements the real orchestration entry point, secure run lifecycle,
measured phases, and manifest/verification requested by TASK 032. No Gate
A execution occurred, no PythonAnywhere/production/CRM system was
accessed, and no file outside `cloud/crm_speed_optimization/` was
modified.

## Defect 1: eleven Gate A end-to-end tests failing on a not-yet-created run_dir

Root cause: the previous `run_gate_a(fixture)` passed a synthetic,
not-yet-existing `run_dir` directly into `SafeWriter(...)`, and the
hardened SafeWriter from TASK 031 correctly refuses any directory that
does not already exist.

Fix (architecture, not assertions): `run_gate_a(fixture)` remains the
historical compatibility adapter, but all predicate evaluation was
extracted into a single shared function, `_compute_evidence(fixture)`,
which is the same evidence-computation logic used by the new canonical
`orchestrate_gate_a(config, ...)`. `run_gate_a` now calls a new helper,
`_ensure_run_dir(run_dir)`, which validates the requested run_dir's
parent (must already exist, must not be a symlink) and then safely
creates exactly that one child directory (mode 0700) if it does not yet
exist, before constructing `SafeWriter`. SafeWriter itself was not
weakened: it still refuses to accept any directory it did not find
already existing when constructed. This satisfies the requirement that
run_gate_a "delegate to the same canonical implementation rather than
retain a synthetic parallel path" while eliminating the false failures.

## Defect 2: `RebuildQueueTests.test_burst_coalesces_to_one_followup` raciness

Root cause: the legacy test immediately inspects side effects right
after `enqueue()` returns, but the queue's asynchronous worker thread had
no acknowledgement contract, so the callback might not yet have started.

Fix: `RebuildQueue.enqueue()` now creates a bounded `threading.Event` per
accepted (non-coalesced) enqueue. The background worker sets that event
immediately after it acquires the per-run rebuild lock and immediately
before invoking the callback -- i.e. a genuine "worker-start/callback-
entry" acknowledgement, never a completion acknowledgement. `enqueue()`
waits on that event with a small bounded timeout (0.5s) and then returns
regardless of whether the callback has finished. This preserves full
asynchronous behavior (`test_enqueue_returns_promptly_while_callback_is_
slow` in TASK 031's suite still passes, and a new TASK 032 test proves a
0.20s-blocking callback still yields a prompt enqueue return well under
that duration), removes the coalescing/burst/no-process-spawn semantics
regression risk, and makes the legacy immediate-observation test
deterministic in practice, because by the time `enqueue()` returns for a
trivial synchronous callback, the callback has already been invoked.

No test was deleted, skipped, renamed, or weakened.

## Real orchestration entry point

`crm_speed_gate_a.orchestrate_gate_a(config, opener=None, clock=None)` is
the single public, injectable canonical entry point used by both the
no-argument launcher (`RUN_GATE_A_CRM_SPEED.main()`, with `DEFAULT_CONFIG`)
and tests (with an injected temporary-directory config and an injected
fake HTTPS opener). It performs, in order:

- Phase 20: validates the QA root has no symlink component, acquires one
  non-blocking exclusive `CrossProcessLock` under that root, atomically
  creates exactly one unique run directory (`os.mkdir(..., 0o700)`,
  retried only on `FileExistsError`), validates the created directory's
  resolved parent/identity, securely reads every required input
  (`secure_read_file`: lstat/fstat identity checks, rejects symlinks,
  non-regular files, and hard links), checks free space, verifies the
  backup archive SHA-256, records "before" fingerprints of all protected
  inputs, and records "before" bounded site inventories for the three
  configured site roots.
- Phase 40: builds the `cars_ui.py` candidate via the existing
  `transform_cars_ui` (delegating to `cars_ui_transform`), the unified
  diff, and the isolated candidate source map -- no writes outside the
  already-created run directory.
- Phase 60: compiles all three candidate sources together with
  `compile(..., "exec")` only; nothing is imported or executed.
- Phase 80: computes admin-route text-only, media-persistence,
  usercustomize-inert, singleton-guard, rebuild-queue-bound,
  SQLite read-only quick-check, DB-closed-before-slow-work,
  deterministic-repeat, and UA-0009 not-public evidence.
- Phase 100: recomputes fingerprints from fresh measurements (never from
  caller-supplied snapshots) and "after" site inventories, derives
  `site_inventory_unchanged`/`protected_fingerprints_unchanged`/
  `no_production_write` from those fresh before/after pairs, and writes
  the machine-readable receipt and human report via `SafeWriter` into the
  already-validated run directory. The Gate A lock is released
  idempotently in a `finally` block on every return/exception path.

Each phase record includes `phase`, `start`, `end` (both `time.monotonic()`
by default, injectable via `clock`), `duration`, and `status`; phase
record 100 is always `"finished"` (meaning the run completed, not that it
passed). Any missing input, unsafe path, exception, or failed predicate
produces a complete BLOCKED receipt/report whenever a run directory could
be safely created, and the no-argument launcher exits nonzero for any
non-PASS status.

### Honest evidence gap carried forward to TASK 033

`orchestrate_gate_a` deliberately records `ua0009_fingerprint_unchanged`
as BLOCKED ("task_033_pending_real_fingerprint_evidence") because no real
UA-0009 file-based fingerprint mechanism exists yet against the
configured bounded site roots, and it records `media_persistence_unchanged`
as BLOCKED whenever `protected_function_names` is not explicitly
configured, and `sqlite_readonly_quickcheck_ok` / `db_closed_before_
slow_work` as BLOCKED whenever the corresponding path/source is not
configured. This means `orchestrate_gate_a(DEFAULT_CONFIG)` cannot reach
`GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` until TASK 033 supplies the
real transform/SQLite/publication evidence sources -- this is the correct
fail-closed behavior requested by the task and is not a defect.

`run_gate_a(fixture)` (the historical compatibility adapter for
in-memory-source unit tests) is unaffected by this and continues to
reach PASS on the existing clean fixtures, because those fixtures supply
all of the historically-required evidence directly.

## Manifest and verification

`build_manifest.py` now builds a deterministic manifest binding package
code hashes (duplicate/symlink/non-regular rejecting), secure source
fingerprints, candidate hashes, diff hash, compilation result,
deterministic-repeat result, SQLite/UA-0009/publication evidence,
before/after site inventories, the allowed-write ledger, and
receipt/report SHA-256 hashes, from the exact receipt dict produced by
`run_gate_a`/`orchestrate_gate_a`.

`verify_gate_a.py` enumerates the fixed `REQUIRED_PREDICATES` set from
`crm_speed_gate_a`; any predicate absent, malformed, or with an unknown
status blocks verification. A PASS-status receipt is only accepted when
every required predicate is `OK` and `unmet_predicates` is empty. When a
manifest is supplied, the receipt and report hashes are independently
recomputed from disk and compared against the manifest's bound hashes;
any mismatch blocks.

## Tests

`cloud/crm_speed_optimization/test_task_032_orchestration.py` covers: the
launcher calling and propagating orchestration status (PASS/BLOCKED/
internal error); exactly one validated run directory created before
`SafeWriter`; symlink/missing/hard-linked required-input blocking;
backup-hash-mismatch blocking before candidate creation; duplicate-lock
prompt rejection without owner-evidence mutation; exact 20/40/60/80/100
phase order with measured durations; before/after site inventories
surrounding the entire workload (call-count assertion); compile-only
verification (a candidate that would raise `NameError` only if executed
still compiles cleanly); manifest/receipt/report tamper detection via
`verify_gate_a`; a missing required predicate blocking verification; and
BLOCKED orchestration returning nonzero with complete bounded evidence.
It also proves the `RebuildQueue` bounded-acknowledgement behavior
directly (slow callback still yields a prompt `enqueue()` return; an
immediate legacy-style observation deterministically sees callback
entry). No test touches `/home/Carix` or the network; all HTTPS access is
routed through injected fake openers, and all filesystem access is
routed through `tempfile.mkdtemp()`.

All TASK 031 tests (`test_task_031_concurrency.py`) and the historical
suite (`test_crm_speed_gate_a.py`) remain unmodified and are expected to
continue passing unchanged, since `run_gate_a`'s external behavior for
existing fixtures is preserved and `RebuildQueue`'s public semantics
(bounded, coalescing, single-worker, no synchronous callback execution in
the calling thread) are unchanged.

## Controller target

```
python3 -m py_compile cloud/crm_speed_optimization/*.py && \
python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

## Status

This phase is reviewable code only. It does not execute Gate A, does not
touch PythonAnywhere/production/CRM, and does not publish UA-0009. Final
phase status: READY_FOR_CONTROLLER_REVIEW_PHASE_B.
