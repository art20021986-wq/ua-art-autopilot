# TASK 031 — CRM-SPEED-001 phase A report

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Scope

This is phase A of the TASK 030 repair, split into independently
committable phases per owner-approved direction. This phase implements
only the canonical concurrency primitives (`CrossProcessLock`,
`SingletonGuard`, `RebuildQueue`) and the secure `SafeWriter`, plus
compatibility re-export modules and an executable offline test suite.

Status of this phase: **READY_FOR_CONTROLLER_REVIEW_PHASE_A**. This is
**not** READY_FOR_GATE_A and does not authorize Production acceleration.
Later phases (integration with the launcher/orchestrator entry points and
any remaining probes) plus independent controller review remain
required before Gate A can be considered.

## What changed and why

The previous package (reviewed under TASK 030) had:

1. **Unsafe lock takeover** — the old `acquire()` read evidence, then
   separately unlinked/re-created the file without any cross-process
   serialization, allowing a TOCTOU race between two processes both
   deciding the owner was stale.
2. **Synchronous queue execution** — the old `RebuildQueue.enqueue()`
   called `_drain()` inline, meaning `enqueue()` blocked for the full
   duration of a slow callback instead of returning promptly.
3. **Hard-link acceptance** — the old `SafeWriter` never checked
   `st_nlink`, so a hard-linked target could be silently rewritten,
   affecting the other link.
4. **Incomplete lifecycle** — `singleton_guard.py` referenced
   `label=`, `try_acquire()`, and `install_signal_handlers()` on
   `CrossProcessLock`, none of which the canonical class actually
   implemented, so the compatibility module could not have worked as
   written.

### CrossProcessLock (canonical_modules.py)

- All owner inspection, stale-takeover decisions, and evidence writes
  happen while holding an exclusive `fcntl.flock(LOCK_EX | LOCK_NB)` on a
  validated regular guard file (`<lock_path>.guard`, opened with
  `O_NOFOLLOW`). No unlink/read/unlink TOCTOU remains.
- Owner evidence: PID, `/proc/<pid>/stat` start-time field, a
  `secrets.token_hex(16)` ownership token, and acquisition timestamp.
- `_owner_status()` classifies evidence as `absent`, `live`, `dead`, or
  `unknown`:
  - `live` (PID alive AND start-time matches) is **never** stolen, even
    if `stale_after_seconds` has elapsed — age is not consulted for a
    verified-live owner.
  - `dead` (PID confirmed not alive, OR PID alive but start-time
    mismatch — i.e. PID reuse) may be taken over.
  - `unknown` (liveness or identity cannot be determined, e.g. `/proc`
    unreadable) fails closed: `acquire()` returns `False`, exactly like
    `live`. Unknown evidence is never used to positively declare
    staleness.
- A duplicate concurrent `acquire()` returns `False` promptly (bounded
  by a single non-blocking `flock` attempt) and never mutates the owner
  record.
- `release()` only removes the record if the currently-stored token
  matches this instance's token (foreign-token release is a safe no-op).
- `release()` is idempotent, exception-safe, and never raises. It checks
  that the parent directory still exists before doing anything and never
  recreates a deleted parent. Registered once via `atexit`.
- `try_acquire()` alias and `install_signal_handlers()` /
  `restore_signal_handlers()` compatibility helpers were added directly
  on `CrossProcessLock` so historical `singleton_guard.py` call patterns
  now actually work against real methods.
- Optional `__enter__`/`__exit__` context-manager support was added
  without changing existing constructor/acquire/release signatures.

### SingletonGuard

- Subclasses `CrossProcessLock` directly (same canonical lock
  semantics).
- Explicit `install()` (acquire + install signal handlers) and
  idempotent `cleanup()` (restore handlers + release). Nothing runs at
  import time.
- Signal handling only wraps `SIGTERM`/`SIGINT` when available, stores
  and restores the previous handler instead of discarding it, and never
  calls `os.kill` on any process.

### RebuildQueue

- `enqueue()` now only flips a `pending` flag under a `threading.Condition`
  and lazily starts a single bounded background worker thread; it never
  runs the callback inline and never spawns a thread per call.
- The worker loop consumes at most one pending flag per iteration
  (coalescing bursts into a single follow-up run) and wraps each
  callback invocation with the canonical `CrossProcessLock` around the
  critical section.
- Callback exceptions are caught, truncated to 500 characters, appended
  to `self.errors`, optionally forwarded to a supplied `error_handler`,
  and never retried automatically — no spin, no recursive drain.
- `shutdown(timeout=...)` provides deterministic bounded join behavior
  for tests.

### SafeWriter

- Rejects absolute paths and `..` traversal before touching the
  filesystem.
- Walks the relative path component-by-component from the validated run
  directory, rejecting any symlinked intermediate component and
  refusing to blindly `makedirs` through an attacker-controlled chain
  (each directory is created one level at a time only after being
  confirmed non-symlink).
- Rejects an existing target that is a symlink, non-regular file, or has
  `st_nlink != 1` (hard link) before writing anything.
- Writes through an exclusive (`O_CREAT | O_EXCL`), no-follow
  (`O_NOFOLLOW`), mode-`0600` temporary file inside the validated target
  directory, validated again via `fstat`.
- Re-validates target-directory identity and target safety immediately
  before `os.replace()`, closing the replacement-race window; a test
  hook (`_pre_replace_hook`, used only by the test suite) deterministically
  injects such a race and proves it is rejected.
- fsyncs the file and the containing directory, then performs the
  atomic rename.
- Cleans up the temporary file on any failure path.
- Maintains an exact `self.ledger` list of `{relative_path, size, sha256}`
  entries for every successful write.
- Exposes no production-write capability; the constructor requires an
  already-existing, non-symlink directory supplied by the caller (tests
  use `tempfile.mkdtemp`).

## Test evidence

`cloud/crm_speed_optimization/test_task_031_concurrency.py` exercises the
real canonical classes only (no mocking of the classes under test, only
a single monkeypatch of `_process_start_time` to deterministically
simulate an unknown-identity condition):

1. Live owner (matching PID + start identity) survives an already-expired
   `stale_after_seconds`.
2. Dead-owner stale takeover (PID does not exist).
3. PID-reuse / start-time mismatch takeover.
4. Unknown identity fails closed (`acquire()` returns `False`).
5. Foreign token cannot release; real owner's evidence is untouched.
6. Release / double release / exception cleanup / simulated atexit
   cleanup / deleted-parent cleanup — none raise, none recreate the
   deleted parent.
7. Deterministic multiprocess barrier: 100 rounds x 4 forked contenders
   each, synchronized with `multiprocessing.Barrier`; exactly one winner
   per round, held until all contenders in that round have attempted.
8. Slow callback proves `enqueue()` returns in well under 0.5s while the
   callback blocks on an event for up to 3s.
9. Burst of 11 rapid `enqueue()` calls while a callback is gated produces
   exactly 2 runs (one active, one coalesced follow-up) and
   `coalesced >= 1`.
10. A callback that always raises executes exactly once per enqueue, is
    recorded in `errors`, and is never retried automatically.
11. SafeWriter rejects: symlinked parent, symlinked target, hard-linked
    target, non-regular (FIFO) target, traversal, absolute path, and a
    deleted run directory.
12. A deterministically injected pre-replace race (target swapped for a
    symlink between temp-file completion and the atomic rename) is
    rejected.
13. A successful write is byte-exact, mode `0600`, `st_nlink == 1`, and
    recorded in the ledger with the correct size and SHA-256.
14. Compatibility imports from `cross_process_lock.py`, `rebuild_queue.py`,
    `safe_writer.py`, and `singleton_guard.py` resolve to the exact same
    canonical class objects (`assertIs`).

Controller command to reproduce:

```
python3 -m py_compile cloud/crm_speed_optimization/*.py && \
  python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

## Compatibility

- All previously-existing public imports/classes/constructor and
  acquire/release signatures used by the existing 73-test suite are
  preserved.
- `cross_process_lock.py`, `rebuild_queue.py`, `safe_writer.py`, and
  `singleton_guard.py` remain thin re-export/compatibility modules that
  delegate to `canonical_modules.py`; none carry divergent lock logic.
- No existing test was deleted, skipped, renamed, or weakened.

## Explicit non-claims

- No PythonAnywhere access occurred. No network access occurred.
- Production, CRM, `crm.db`, bot, site, media, cards, generators, WSGI,
  processes, scheduled tasks, and UA-0009 were not touched.
- Gate A was not executed. This phase does not claim
  READY_FOR_GATE_A or production acceleration.
- Remaining phases (any launcher/orchestrator integration work not
  covered here) and independent controller execution/review of this
  phase are still required.

Final phase status: **READY_FOR_CONTROLLER_REVIEW_PHASE_A**.
