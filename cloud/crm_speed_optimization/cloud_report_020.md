# cloud_report_020.md — CRM-SPEED-001 round 2 corrective report (task_025)

## Context

Commit 6207fc5a6b1f540475116d646261f37181a6bb22 (round 1 corrective
package, task_024) was independently controller-executed. The result:

- Python compilation passed.
- The first full unittest run already failed:
  `CrossProcessLockTests.test_simultaneous_stale_takeover_only_one_wins`
  expected exactly 1 winner, observed 3 — because the test's subprocess
  choreography allowed sequential (non-overlapping) successes to be
  miscounted as simultaneous.
- Multiple `atexit` callbacks raised `FileNotFoundError` opening
  `<tmp>/test.lock.guard` after `TemporaryDirectory` cleanup.
- The 10/10 required run count was never reached.
- Several Gate A predicates were unconditional `True` placeholders
  (`site_inventory_unchanged`, `no_production_write`,
  `repeat_runs_byte_identical`, `singleton_guard_present`,
  `no_process_spawn_in_rebuild_path`, `db_handles_closed_before_slow_work`,
  `media_persistence_functions_unchanged`).
- The publication probe treated connection errors as "not served" —
  ambiguity, not proof.
- Candidate transforms for usercustomize/start_safe/run_all were
  reported as not deeply rewritten.

## What changed in this round

### CrossProcessLock and the stale-takeover test (item 1, item 2)

`CrossProcessLock` in `crm_speed_gate_a.py` was rewritten:

- Stale takeover now goes through a second `O_CREAT|O_EXCL` guard file
  (`<lock>.guard`). Only one contending process can pass the takeover
  critical section at any instant; every other contender's `os.open`
  raises `FileExistsError` and it returns `False` immediately without
  touching the lock file. This removes the possibility of more than one
  "winner" during a race, which was the root cause of the round-1
  failure (3 successes instead of 1).
- `test_simultaneous_stale_takeover_only_one_wins` was rewritten as a
  true multiprocess barrier/handshake: N independent `multiprocessing`
  processes each set a `ready` event, wait on one shared `start` event,
  then race `acquire(timeout=0)`. The parent collects all N results
  *before* releasing a `hold` event that lets the winner actually
  release its lock, guaranteeing every contender has already attempted
  while the winner still holds ownership. The parent also polls the
  lock file's `pid`/`token` fields during a 1-second hold window and
  asserts they never change. After the winner releases, a fresh
  fifth process is spawned and must acquire successfully.
- A second stress test repeats an equivalent race 100 times using the
  `fork` context for speed, asserting exactly one winner every round.
- `release()` and the `atexit` handler are now wrapped so they can never
  raise: `release()` reads the lock file inside a `try/except
  Exception`, treats `FileNotFoundError`/`OSError` as already-clean, and
  the `atexit`-registered callback (`_atexit_release`) wraps the whole
  call in `try/except Exception: pass`. Explicit `release()` also
  unregisters the `atexit` callback via `atexit.unregister`, so a normal
  exit never re-invokes cleanup on a directory that may already be gone.
  Behavioral tests cover: explicit release + directory cleanup, simulated
  atexit call after cleanup, repeated release, and foreign-token release
  (must not delete a lock that now belongs to someone else).

### Evidence-derived predicates, no fabricated True (item 3)

A new `Evidence` class replaces every unconditional boolean. Each
required predicate in `build_receipt()`
(`required_inputs_present`, `backup_archive_verified`,
`site_inventory_unchanged`, `ua0009_not_public`, `sqlite_quick_check`,
`protected_inputs_unchanged`) is produced only through `Evidence.record()`
+ `Evidence.finalize(condition)`, where `condition` is always derived
from a real measurement (file existence, hash comparison, HTTP probe
result, `PRAGMA quick_check` result). `Evidence.fail()` is sticky: once
called, no later `finalize(True)` can flip the result. Tests
(`EvidenceFrameworkTests`) mutate individual measurements and confirm the
final boolean flips to `False`/`BLOCKED`.

### Real bounded site/public inventory (item 4)

`scan_bounded_inventory()` performs a non-recursive `os.scandir` over the
three fixed roots, matches only the exact allowed filename set
(`index.html`, `katalog.html`, `UA-0001..0009.html` and their `-diag`/
`-track` variants), enforces the 32-file cap per root, rejects symlinks,
non-regular files, and multi-link (`st_nlink != 1`) files, and records
canonical path/mode/size/mtime_ns/sha256. `inventories_equal()` does a
byte-for-byte sorted comparison. Missing roots, overflow, symlinks, and
hard links all produce blocked reasons and are covered by dedicated
tests.

### Fail-closed publication probe (item 5)

`probe_ua0009_not_public()` uses a `urllib` opener with a
`HTTPRedirectHandler` that returns `None` (so any 3xx becomes an
`HTTPError`, not a followed redirect). Only `HTTPError` with code 404 or
410 passes. Every other observable outcome — 2xx, 5xx, redirect, DNS
failure, connection refused, timeout, TLS error, malformed URL,
non-HTTPS URL, missing URL — is mapped to `passed = False` with a
specific recorded reason. `UA0009_CANONICAL_URL` must be supplied
explicitly via environment variable; Gate A does not guess it. Tests
cover connection-refused (via a closed local socket), 404 pass, 200
block, redirect block, and timeout block.

### Real candidate transforms (item 6)

Five AST-based, anchor-driven transforms were implemented in
`crm_speed_gate_a.py`. They operate generically on whatever real source
Gate A reads at execution time — they are not hardcoded to assumed file
content:

- `transform_usercustomize`: walks top-level statements; keeps only
  whitelisted-stdlib imports, function/class definitions, and pure
  constant assignments; drops forbidden application imports; BLOCKs on
  any unclassified top-level call, `if` guard, or import.
- `transform_singleton_wrap`: requires exactly one
  `if __name__ == "__main__":` block whose body is exactly one
  `Expr(Call)` statement; wraps that call in `SingletonGuard.run(...)`;
  BLOCKs on zero or multiple/ambiguous guards.
- `transform_avtoperedacha_rebuild`: requires exactly one
  `subprocess.*`/`multiprocessing.*`/`os.system` call anywhere in the
  module; replaces it with `REBUILD_QUEUE.enqueue()`; re-parses the
  result and BLOCKs if any process-spawn call remains reachable.
- `transform_cars_ui_admin_routes`: for each of the four named routes,
  rewrites simple top-level `Expr`/`Await` statements that call a
  known media-send method/name to a text-only reply; BLOCKs the whole
  candidate if a route is missing, a media call is buried in a
  non-trivial expression, or dynamic dispatch (`getattr(...)`) is used;
  re-verifies after transform that no media-send name remains reachable
  in the route function body.
- `transform_db_short_ownership`: for straight-line functions only
  (BLOCKs immediately on `for`/`while`/`try`), locates a
  `sqlite3.connect(...)`-style assignment, finds the first subsequent
  "slow call" keyword, and inserts `<conn>.close()` immediately before
  it if not already closed; BLOCKs if the DB variable is referenced
  again after the slow call (ambiguous ownership).

All five are exercised against synthetic fixtures (clean pass and
deliberate-BLOCK cases) in `test_crm_speed_gate_a.py`.

### Deterministic repeat measurement (item 7)

`measure_deterministic_repeat()` runs a transform 10 times from the exact
same source bytes, hashes each candidate (or records `BLOCKED` +
reasons), and only reports `passed = True` when all 10 outcomes are
identical. A deliberately nondeterministic fixture transform is included
and proven to BLOCK.

### no_production_write derivation (item 8)

`build_receipt()` derives the closest available production-write-safety
evidence from: before/after fingerprints of every bounded protected
input (`protected_inputs_unchanged`), before/after bounded site
inventory (`site_inventory_unchanged`), and `SafeWriter.audit_all_under_run_dir()`
which records every path actually written and asserts each one resolves
under the run directory. No boolean is set without these measurements.

### End-to-end coverage (item 9)

`EndToEndFixtureTests` builds a synthetic fixture (three site roots, a
real SQLite DB) and proves `sqlite_quick_check` passes on a healthy
fixture DB and that the fixture DB is byte-identical before and after
evidence collection. This is a genuine but intentionally smaller-scope
end-to-end proof than the full contract's "all required source files, DB,
backup, three site roots, exact URL probe mock, representative
admin/rebuild/SQLite structures" fixture; see Known limitations below.

## Known limitations (explicit, not hidden)

1. **Controller execution not performed by Claude/Cloud.** This report
   describes what the authored tests are designed to prove when run.
   Claude/Cloud does not execute code against production or claim 10/10
   suite runs on its own authority; that is the controller's role per
   the established pipeline.
2. **cars_ui / DB-ownership transforms are conservative by design.** They
   correctly BLOCK on any control-flow shape more complex than a
   straight-line function or a single top-level statement call. Real
   production files may legitimately BLOCK on first execution if their
   actual structure is more complex; that is a safe, correct outcome per
   the task's own rule ("ambiguous => BLOCKED"), not a defect to hide.
3. **The full contractually-described end-to-end fixture** (every
   bounded source file, backup, three site roots, URL probe mock, and
   representative admin/rebuild/SQLite structures wired together into one
   single-run scenario) is not fully assembled in this round; only a
   focused subset (SQLite fixture + inventory fixture roots) is provided.
   Building the complete fixture is the next concrete step before this
   package can be called fully done against item 9's full scope.

## Final status

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

STATUS: READY_FOR_CONTROLLER_REVIEW

This is not READY_FOR_GATE_A_EXECUTION and not a claim that production is
fixed. The package must go through the same independent controller
execution process as prior rounds before any Gate A run is authorized.
