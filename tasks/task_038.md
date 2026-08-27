# TASK 038 — CRM-SPEED-001 real candidate transforms and RebuildQueue cleanup

## Authority and immutable safety boundary

Continue the already owner-approved CRM-SPEED-001 repair. This is reviewable code only. Work only under `cloud/crm_speed_optimization/` plus `cloud/latest_status.md` and `cloud/owner_reply.md`.

Do **not** execute Gate A. Do **not** access PythonAnywhere or the network. Do **not** install candidates. Do **not** modify Production, CRM, `crm.db`, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Do not modify `tasks/`. Tests use only temporary local fixtures and fake openers.

Required markers in every report/status:

```text
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

All implementation must be Claude-authored. Return complete files, not patches or excerpts.

## Independent controller verdict on commit ad4a7d8aa01eb4c5901b49d7a74ce10af5f19a01

Compilation passed and full discovery reported 188/188 PASS in 39.376 seconds. The package is nevertheless **not accepted** because the green suite missed two executable architecture defects.

### Defect A — escaped background-thread exception

During `test_burst_coalesces_to_one_followup`, `RebuildQueue._loop` emitted an unhandled daemon-thread traceback after the temporary parent directory was removed:

```text
ValueError: parent directory does not exist: /tmp/...
```

Root cause: `lock = CrossProcessLock(self._lock_path)` is outside the worker's `try`. The exception escapes `threading.Thread`, while unittest still exits zero. A green test command therefore does not prove clean background lifecycle.

### Defect B — phase40 does not generate the required real candidates

Manual source audit proved that `crm_speed_gate_a.orchestrate_gate_a.phase40`:

- transforms only `cars_ui.py`;
- reads only one of the two `usercustomize.py` inputs;
- copies `usercustomize.py` and `avtoperedacha.py` unchanged as supposed candidates;
- ignores `start_safe.py`, `run_all.py`, and `samokontrol.py` entirely;
- does not integrate singleton lifecycle into launcher candidates;
- does not bind a real in-process generator callback to one `RebuildQueue` or replace process-spawn rebuild paths;
- does not apply short SQLite ownership transforms to `avtoperedacha.py` and `samokontrol.py`;
- repeats only the cars-ui transform, rather than all required transforms;
- verifies predicates against original source instead of the generated candidates;
- does not write every candidate and unified diff to the isolated run directory.

This violates TASK 030 even though tests pass. Fix executable behavior, not only reports or tests.

## 1. RebuildQueue: no escaped thread exception, no spin

Correct the single canonical implementation in `canonical_modules.py`; compatibility modules must continue to re-export the same class.

Requirements:

- Enclose lock construction, acquisition, callback, release and worker-state cleanup in a complete exception boundary.
- If the lock parent disappears or lock construction/acquisition fails, set the pending acknowledgement event, record one bounded sanitized error (exception class/category only; no production path, secrets or PII), clear running/pending safely, notify waiters, and terminate that worker iteration without retry/spin.
- No exception may reach `threading.excepthook`.
- `enqueue()` remains prompt and bounded; callback remains mandatory; at most one active and one coalesced follow-up; callback errors remain one bounded error with no recursive retry.
- `shutdown()` remains idempotent and does not recreate a deleted parent.
- Add a deterministic regression that installs a temporary `threading.excepthook` spy, deletes the lock parent before enqueue/worker construction, waits for the worker, and proves: zero excepthook calls, worker stops, queue becomes idle/stopped, one sanitized error, no callback, no spin, no parent recreation.
- Preserve all existing concurrency tests, including the 100-round multiprocess lock test.

## 2. One canonical fail-closed candidate-transform module

Create `candidate_transforms.py`. It must be standard-library-only, deterministic, AST/token-aware, and must never import/execute an input application source. Regex may be used only after an AST anchor has established an exact byte span; broad regex rewriting is forbidden.

Use one stable transform result contract everywhere:

```python
{
    "status": "OK" | "BLOCKED",
    "candidate": str | None,
    "reasons": [bounded deterministic strings],
    "metadata": {bounded deterministic structural evidence}
}
```

On missing/ambiguous/unsupported anchors return `BLOCKED` with `candidate=None`; never silently pass through an unsafe original as an accepted candidate. Reasons and metadata must never contain source bodies, secrets, PII or absolute production paths.

### 2.1 Both usercustomize candidates

Generate two distinct candidates and logical names:

- `usercustomize_py310.py` mapped to the exact `/python3.10/.../usercustomize.py` input;
- `usercustomize_py313.py` mapped to the exact `/python3.13/.../usercustomize.py` input.

For each:

- remove known unconditional application/background imports or startup effects for `team_bot`, `run_all`, `start_safe`, `avtoperedacha`, `stranica`, process/thread/subprocess workers and equivalent statically resolved aliases;
- preserve only a module docstring, `__future__` imports, provably harmless imports/customization, pure literal assignments and inert definitions with no decorators/default/annotation expressions that execute unknown code;
- any unclassified top-level expression/call/context manager/loop/try/with/decorator/dynamic import or other possible side effect must BLOCK;
- resulting import behavior must be inert and statically verified; an original forbidden import cannot remain in the candidate.

Known forbidden startup removed is an OK transform. Unknown behavior is not removed speculatively; it BLOCKS.

### 2.2 `start_safe.py` and `run_all.py` singleton candidates

For each source:

- require exactly one structural `if __name__ == "__main__"` entry anchor and no import-time application/process/thread/network/DB/filesystem mutation outside inert definitions/constants/imports;
- transform that exact entry into one explicit wrapper using `SingletonGuard` from the generated support candidate described below;
- both launchers must use the same deterministic application lock path below `/home/Carix/qa/crm_speed_task020`, so starting through either launcher cannot create duplicate BOT CRM runtimes;
- duplicate start exits promptly with one defined nonzero code and bounded diagnostic;
- release is guaranteed for normal return, `SystemExit`, exception, atexit and supported signals through the canonical lifecycle; no lock is acquired at import;
- `os._exit`, ambiguous/dynamic entry dispatch, multiple main anchors or missing anchors BLOCK.

### 2.3 Generated runtime support candidate

Generate deterministic `crm_speed_runtime.py` containing the minimum canonical `CrossProcessLock`, `SingletonGuard` and `RebuildQueue` runtime needed by the launcher and rebuild candidates. It must preserve the already-audited token/PID/process-start/flock semantics and the corrected no-escaped-exception queue behavior.

It is an explicit eighth candidate: compile it, hash it, write it, include it in receipt/report/manifest/install mapping, and make all generated candidates import this filename. Candidates must not depend on a module available only inside `cloud/crm_speed_optimization/`.

Generating this support source must be deterministic and must not acquire a lock, start a thread or perform I/O.

### 2.4 `avtoperedacha.py` rebuild candidate

Implement a conservative structural transform:

- identify exactly one existing distinct in-process `stranica` generation callable/call path using imports/definitions/call graph; do not execute it in Gate A;
- bind that callable through a zero-argument wrapper to exactly one module-level `RebuildQueue` using `crm_speed_runtime.py`; constructing the queue at import must not start its worker;
- replace every structurally proven subprocess/`os.system`/multiprocessing/shell rebuild path for that same generator with immediate `_queue.enqueue()`; preserve handler return behavior where structurally provable;
- remove now-unused process-spawn imports only when their use count proves they belonged solely to replaced rebuild paths;
- statically prove no subprocess, `os.system`, multiprocessing, shell or dynamic equivalent remains reachable in the rebuild call graph;
- multiple possible generator callbacks, ambiguous aliases, dynamic command construction, unrelated process-spawn usage that cannot be preserved safely, or import-time generator execution BLOCK.

The transform must preserve the existing in-process generator behavior/path and must never run it during transformation/tests.

### 2.5 Short SQLite ownership for `avtoperedacha.py` and `samokontrol.py`

Upgrade the canonical structural implementation in `sqlite_ownership.py` and use it from `candidate_transforms.py`; do not create a second divergent SQLite transformer.

Requirements for each configured/structurally discovered DB function:

- require unambiguous connection/cursor/SELECT/fetch anchors and supported straight-line or explicitly handled control flow;
- apply a short explicit SQLite timeout when a local connection is created;
- materialize fetched rows into ordinary immutable values before DB close;
- close every cursor and connection/transaction in `finally`, on every return/exception path, before formatting, hashing, sleep, Telegram/network calls, page generation or filesystem work;
- no unnecessary write transaction or mutable PRAGMA may be added; preserve query and parameter semantics;
- a connection supplied by the caller may not be silently closed unless exact ownership is structurally proven; otherwise BLOCK;
- unsupported branch/loop/try/with/alias/escape/dynamic handle use BLOCK;
- verification must be handle-specific and path-conservative, not satisfied by seeing an unrelated `.close()` anywhere.

Preserve the historical public names `AnchorNotFoundError`, `find_db_handle_names`, `verify_no_live_handle_across_slow_call`, and `transform_short_ownership`, tightening behavior as needed.

## 3. Integrate all real candidates into the one orchestrator

Modify `crm_speed_gate_a.py` without creating a parallel Gate A implementation.

### Fixed source resolution

- Resolve exactly two `usercustomize.py` paths by their Python 3.10 and 3.13 parent components; never choose only the first basename match.
- Resolve exactly one each of `start_safe.py`, `run_all.py`, `cars_ui.py`, `avtoperedacha.py`, and `samokontrol.py` from the already securely read required-input records.
- Missing/duplicate/ambiguous mapping BLOCKS.

### Phase40

- Transform all seven production-source candidates plus the generated support candidate from exact securely read bytes.
- `cars_ui.py` must still use `cars_ui_transform.transform_cars_ui` as the only canonical admin-media transformer; do not duplicate that logic in `candidate_transforms.py`.
- If any transform is BLOCKED, final status remains BLOCKED and no original unsafe source may be labeled an accepted candidate. For compatibility, safe compile-only evidence may still be recorded from original bytes with `candidate_origin=original_due_to_transform_block`, as current tests require; that evidence can never satisfy final candidate predicates.
- On complete transform success, write every candidate and every unified diff through `SafeWriter` only, below `candidates/` and `diffs/` in the already-created run directory. No production path write.
- Preserve an exact deterministic logical-name → original-path mapping and logical-name → candidate filename/install target mapping without leaking source content.

### Phase60

- Compile all eight candidate sources together with stable logical filenames, without importing or executing any candidate or application module.
- Compilation evidence must list all eight names and hashes.

### Phase80 evidence must inspect candidates, not originals

- `usercustomize_inert`: both generated usercustomize candidates.
- `singleton_guard_present`: both launcher candidates statically use the same generated runtime/support and common lock, plus the existing canonical behavioral singleton test.
- `rebuild_queue_bound_no_process_spawn`: generated avtoperedacha candidate proves exactly one queue and the exact callback binding/reachability.
- `db_closed_before_slow_work`: generated avtoperedacha and samokontrol candidates using the canonical handle/path-conservative verifier.
- cars-ui media/text predicates: the generated cars-ui candidate while protected upload/save/delete/reference functions remain unchanged.
- `deterministic_repeat_all_transforms`: all seven input transforms plus support generation, each repeated at least 10 times from identical original bytes. Compare candidate bytes, unified-diff bytes, status/reasons and metadata hash. Store the bounded records in the receipt, not merely a boolean/list of names.

Any missing/malformed/non-OK evidence BLOCKS. Preserve compatibility of `_compute_evidence()`/`run_gate_a()` for historical tests, but do not let that synthetic adapter replace or weaken real orchestration.

### Receipt/report and safe writes

- Record per-candidate original SHA-256, candidate SHA-256, diff SHA-256, transform status/reasons/metadata hash, compilation status, deterministic records, support-module install requirement and exact allowed-write ledger.
- Keep PII/source bodies/absolute secrets out of reports.
- Candidate/diff files and receipt/report are the only workload artifacts; all remain in the isolated run directory.
- `PRODUCTION_WRITE: NO` remains mandatory. Gate A final status is still only `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` or `BLOCKED`; this task must not claim either was executed against production.

## 4. Mandatory offline executable regressions

Add `test_task_038_real_candidates.py`. Do not delete, rename, skip, weaken or rewrite any existing test. Tests must be bounded, deterministic, standard-library-only, temporary-directory-only and network-free.

At minimum prove:

1. Deleted RebuildQueue parent causes zero `threading.excepthook` calls, no callback/spin/recreation, one bounded error, clean shutdown/idle state.
2. Slow callback prompt enqueue and one-active/one-follow-up semantics still pass.
3. Forbidden usercustomize startup is removed for both logical versions; harmless content is preserved; unknown top-level side effect BLOCKS.
4. Two usercustomize paths are resolved distinctly; one/missing/duplicate version BLOCKS.
5. Real-shaped `start_safe.py` and `run_all.py` fixtures receive the same singleton lock/wrapper and compile; missing/multiple/ambiguous main or import-time startup BLOCKS.
6. Real-shaped avtoperedacha fixture with one in-process generator plus subprocess rebuild transforms to one queue and no reachable spawn; the generator is never executed during transform/compile; two callbacks/dynamic/unrelated spawn BLOCK.
7. Real-shaped avtoperedacha and samokontrol SELECT fixtures materialize immutable rows and close cursor/connection before injected slow work on normal and exception paths; ambiguous ownership/control flow BLOCKS.
8. All eight candidates compile without importing them.
9. All eight transforms produce identical candidate/diff/status/reasons/metadata hashes for 10 repeats.
10. A strict fully synthetic temporary config using the same `orchestrate_gate_a` path produces all eight candidate/diff artifacts and leaves every original input/site/DB byte-identical. Use a fake 404/410 opener and configured UA fixture only; never access `/home/Carix`.
11. Transform block cannot be converted to PASS by original-byte compile fallback.
12. Phase80 spies/assertions prove it verifies candidate strings, not original strings.
13. Candidate support module is present in candidate hashes, compile list, report/receipt mapping and future install list.
14. No application candidate is imported/executed and no process/network/production path is touched.
15. Existing full discovery remains green with no unhandled thread traceback after process exit.

Controller command:

```bash
python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

Expected: all existing 188 tests plus every new TASK 038 test PASS, zero FAIL, zero ERROR, zero skipped/expected-failure, and zero `Exception in thread` output before or after the unittest summary.

## 5. Deliverables

Return complete mutually consistent contents for exactly:

- `cloud/crm_speed_optimization/canonical_modules.py`
- `cloud/crm_speed_optimization/candidate_transforms.py`
- `cloud/crm_speed_optimization/sqlite_ownership.py`
- `cloud/crm_speed_optimization/crm_speed_gate_a.py`
- `cloud/crm_speed_optimization/test_task_038_real_candidates.py`
- `cloud/crm_speed_optimization/TASK_038_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Do not modify existing tests or other implementation/docs. `cloud/latest_status.md` and `cloud/owner_reply.md` must say `READY_FOR_CONTROLLER_REVIEW_TASK_038`, not `READY_FOR_GATE_A`, until independent controller tests and source audit pass. Do not claim Production acceleration, deployment, Gate A success, CRM change or UA-0009 readiness.

## Exact current source snapshots

The complete exact current sources follow. CRM-SPEED sources are byte-identical between the audited commit `ad4a7d8aa01eb4c5901b49d7a74ce10af5f19a01` and current repository head `c615fd069ef33d5ad9f95cf238468eb595b275b2`; TASK 037 changed only the separate BOT-LOGISTICS package and shared status files. Preserve compatible public APIs and all non-weakened behavior.


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/canonical_modules.py

```python
"""Canonical implementations shared by the launcher, orchestrator, and
tests for CRM-SPEED-001. This module is the SINGLE source of truth for
CrossProcessLock, SingletonGuard, RebuildQueue, and SafeWriter.

cross_process_lock.py, rebuild_queue.py, safe_writer.py, and
singleton_guard.py are thin re-export/compatibility modules kept only for
backward-compatible imports; they contain no divergent lock logic of
their own.

TASK 031/032. No production imports. No production-write capability.
All writes are confined to explicitly supplied, already-existing local
directories (temporary directories in tests, or a validated already-
existing run directory created by crm_speed_gate_a.orchestrate_gate_a).
"""
from __future__ import annotations

import atexit
import fcntl
import hashlib
import os
import secrets
import signal
import stat
import tempfile
import threading
import time

__all__ = [
    "LockEvidence",
    "CrossProcessLock",
    "SingletonGuard",
    "RebuildQueue",
    "SafeWriter",
]


# ---------------------------------------------------------------------------
# Low level process identity helpers
# ---------------------------------------------------------------------------

def _process_start_time(pid):
    """Best-effort process start-time fingerprint using /proc (Linux).

    Returns None when unavailable; callers MUST treat None as UNKNOWN and
    must never use it to positively confirm liveness or staleness.
    """
    try:
        with open(f"/proc/{pid}/stat", "r") as fh:
            data = fh.read()
        end = data.rfind(')')
        if end == -1:
            return None
        rest = data[end + 2:].split()
        if len(rest) <= 19:
            return None
        return rest[19]
    except Exception:
        return None


def _pid_alive(pid):
    """Tri-state liveness check.

    Returns True (alive), False (confirmed dead), or None (unknown -- must
    fail closed, never treated as a positive staleness signal).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we cannot signal it; it is alive.
        return True
    except Exception:
        return None
    return True


def _owner_status(evidence):
    """Classify the owner evidence as 'absent', 'live', 'dead', or
    'unknown'. 'unknown' MUST be treated as non-stealable (fail closed).
    """
    if evidence is None:
        return "absent"
    alive = _pid_alive(evidence.pid)
    if alive is None:
        return "unknown"
    if not alive:
        return "dead"
    current_start = _process_start_time(evidence.pid)
    if current_start is None:
        return "unknown"
    if not evidence.start_time:
        return "unknown"
    if current_start != evidence.start_time:
        return "dead"
    return "live"


def _validate_parent(path):
    """Validate that the parent directory of path already exists and is
    not a symlink. Returns the resolved real path of that parent. Never
    creates anything.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent == "":
        parent = "."
    if not os.path.isdir(parent):
        raise ValueError(f"parent directory does not exist: {parent}")
    if os.path.islink(parent):
        raise ValueError("parent directory must not be a symlink")
    return os.path.realpath(parent)


class LockEvidence:
    __slots__ = ("pid", "start_time", "token", "acquired_at")

    def __init__(self, pid, start_time, token, acquired_at):
        self.pid = pid
        self.start_time = start_time
        self.token = token
        self.acquired_at = acquired_at

    def to_line(self):
        return f"{self.pid}|{self.start_time}|{self.token}|{self.acquired_at}\n"

    @staticmethod
    def parse(line):
        if not line:
            return None
        parts = line.strip().split("|")
        if len(parts) != 4:
            return None
        pid_s, start_time, token, acquired_at_s = parts
        try:
            return LockEvidence(int(pid_s), start_time, token, float(acquired_at_s))
        except ValueError:
            return None


class CrossProcessLock:
    """Atomic, non-blocking, cross-process lock.

    Owner evidence: PID, Linux process-start identity, a cryptographically
    random ownership token, and an acquisition timestamp. All owner
    inspection, stale takeover, acquisition and release are serialized
    through fcntl.flock(LOCK_EX | LOCK_NB) on a validated regular guard
    file, eliminating unlink/read/unlink TOCTOU races.

    A live owner with matching PID + process-start identity is NEVER
    stolen merely because the record looks old. PID-missing or
    process-start mismatch may be treated as stale only while holding the
    guard serialization lock and only after re-reading evidence. Unknown
    liveness/identity fails closed (never positively declared stale).
    """

    def __init__(self, path, stale_after_seconds=300, label=None):
        self.path = os.path.abspath(path)
        self._validated_parent = _validate_parent(self.path)
        self.guard_path = self.path + ".guard"
        self.stale_after_seconds = stale_after_seconds
        self.label = label
        self.token = secrets.token_hex(16)
        self._owned = False
        self._owned_lock = threading.Lock()
        self._atexit_registered = False
        self._previous_handlers = {}

    # -- guard file plumbing -------------------------------------------------
    def _open_guard(self):
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.guard_path, os.O_CREAT | os.O_RDWR | nofollow, 0o600)
        try:
            st = os.fstat(fd)
        except Exception:
            os.close(fd)
            raise
        if not stat.S_ISREG(st.st_mode):
            os.close(fd)
            raise ValueError("guard path is not a regular file")
        return fd

    @staticmethod
    def _try_flock(fd):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False

    def _read_evidence(self):
        try:
            with open(self.path, "r") as fh:
                return LockEvidence.parse(fh.readline())
        except FileNotFoundError:
            return None
        except Exception:
            return None

    # -- public lifecycle -----------------------------------------------------
    def acquire(self):
        """Return True only if this instance now owns the lock. Never
        blocks indefinitely; a concurrent duplicate acquisition returns
        False promptly and never mutates owner evidence.
        """
        current_parent = os.path.dirname(self.path)
        if not os.path.isdir(current_parent):
            return False
        if os.path.realpath(current_parent) != self._validated_parent:
            return False
        try:
            guard_fd = self._open_guard()
        except Exception:
            return False
        try:
            if not self._try_flock(guard_fd):
                # Another process/thread is inside the critical section.
                return False
            existing = self._read_evidence()
            status = _owner_status(existing)
            if status in ("live", "unknown"):
                return False
            # status in ('absent', 'dead') -> takeover permitted.
            evidence = LockEvidence(
                os.getpid(),
                _process_start_time(os.getpid()) or "",
                self.token,
                time.time(),
            )
            try:
                tmp_fd, tmp_path = tempfile.mkstemp(
                    dir=self._validated_parent, prefix=".lock_tmp_"
                )
            except Exception:
                return False
            try:
                with os.fdopen(tmp_fd, "w") as fh:
                    fh.write(evidence.to_line())
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, self.path)
            except Exception:
                try:
                    if os.path.lexists(tmp_path):
                        os.unlink(tmp_path)
                except Exception:
                    pass
                return False
            recheck = self._read_evidence()
            if recheck is None or recheck.token != self.token:
                return False
            self._owned = True
            with self._owned_lock:
                if not self._atexit_registered:
                    atexit.register(self.release)
                    self._atexit_registered = True
            return True
        finally:
            try:
                fcntl.flock(guard_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(guard_fd)
            except Exception:
                pass

    # backward-compatible alias used by historical callers
    def try_acquire(self):
        return self.acquire()

    def release(self):
        """Idempotent, exception-safe. Only the matching token may remove
        the owner record. Never kills a process, never recreates a
        deleted parent directory, never raises.
        """
        with self._owned_lock:
            if not self._owned:
                return
            self._owned = False
        try:
            parent = os.path.dirname(self.path)
            if not os.path.isdir(parent):
                return
            try:
                guard_fd = self._open_guard()
            except Exception:
                return
            try:
                if not self._try_flock(guard_fd):
                    return
                current = self._read_evidence()
                if current is not None and current.token == self.token:
                    try:
                        os.unlink(self.path)
                    except FileNotFoundError:
                        pass
                    except Exception:
                        pass
            finally:
                try:
                    fcntl.flock(guard_fd, fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    os.close(guard_fd)
                except Exception:
                    pass
        except Exception:
            pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("could not acquire CrossProcessLock")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False

    # -- optional signal-handling compatibility helpers ------------------------
    def install_signal_handlers(self, signals=("SIGTERM", "SIGINT")):
        for name in signals:
            sig = getattr(signal, name, None)
            if sig is None or sig in self._previous_handlers:
                continue
            try:
                previous = signal.getsignal(sig)
            except Exception:
                continue
            self._previous_handlers[sig] = previous

            def _handler(signum, frame, _previous=previous, _self=self):
                _self.release()
                if callable(_previous):
                    _previous(signum, frame)

            try:
                signal.signal(sig, _handler)
            except Exception:
                self._previous_handlers.pop(sig, None)

    def restore_signal_handlers(self):
        for sig, previous in list(self._previous_handlers.items()):
            try:
                signal.signal(sig, previous)
            except Exception:
                pass
        self._previous_handlers.clear()


class SingletonGuard(CrossProcessLock):
    """Process singleton built directly on CrossProcessLock semantics.

    Lifecycle is explicit: call install() to acquire + install signal
    handlers, call cleanup() (idempotent) on normal exit, on exception, or
    let atexit invoke release(). Never installed at import time.
    """

    def install(self):
        if not self.acquire():
            return False
        self.install_signal_handlers()
        return True

    def cleanup(self):
        self.restore_signal_handlers()
        self.release()


class RebuildQueue:
    """Bounded, coalescing, truly asynchronous rebuild queue.

    enqueue() returns promptly. It waits only for a short, bounded
    worker/callback-entry acknowledgement (the worker has acquired the
    rebuild lock and is about to invoke the callback) -- it never waits
    for the callback itself to finish. At most one callback is active at
    a time, executed on a single bounded background worker thread. At
    most one pending follow-up is retained for a burst. The rebuild
    critical section is protected by the canonical CrossProcessLock.
    Callback failures are caught, sanitized (truncated) and recorded;
    there is no infinite retry or recursive drain.
    """

    _ACK_TIMEOUT_SECONDS = 0.5

    def __init__(self, callback, lock_path, error_handler=None):
        if callback is None or not callable(callback):
            raise ValueError(
                "RebuildQueue requires an explicit bound callable callback"
            )
        self._callback = callback
        self._lock_path = lock_path
        self._error_handler = error_handler
        self._cv = threading.Condition()
        self._pending = False
        self._running = False
        self._stopped = False
        self._worker = None
        self._pending_ack_event = None
        self.runs = 0
        self.coalesced = 0
        self.errors = []

    def enqueue(self):
        ack_event = None
        with self._cv:
            if self._stopped:
                return "stopped"
            if self._running:
                self._pending = True
                self.coalesced += 1
                self._cv.notify_all()
                return "coalesced"
            self._pending = True
            ack_event = threading.Event()
            self._pending_ack_event = ack_event
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._loop, daemon=True)
                self._worker.start()
            self._cv.notify_all()
        # Bounded wait for a worker-start/callback-entry acknowledgement
        # only. This never waits for the callback to complete.
        ack_event.wait(timeout=self._ACK_TIMEOUT_SECONDS)
        return "accepted"

    def _loop(self):
        while True:
            with self._cv:
                while not self._pending and not self._stopped:
                    self._cv.wait(timeout=1)
                if self._stopped and not self._pending:
                    return
                self._pending = False
                self._running = True
                ack_event = self._pending_ack_event
                self._pending_ack_event = None
            acquired = False
            lock = CrossProcessLock(self._lock_path)
            try:
                acquired = lock.acquire()
                if ack_event is not None:
                    ack_event.set()
                if acquired:
                    try:
                        self._callback()
                        with self._cv:
                            self.runs += 1
                    except Exception as exc:
                        sanitized = str(exc)[:500]
                        with self._cv:
                            self.errors.append(sanitized)
                        if self._error_handler is not None:
                            try:
                                self._error_handler(exc)
                            except Exception:
                                pass
            finally:
                if acquired:
                    try:
                        lock.release()
                    except Exception:
                        pass
                with self._cv:
                    self._running = False
                    self._cv.notify_all()

    def shutdown(self, timeout=5):
        with self._cv:
            self._stopped = True
            self._cv.notify_all()
        worker = self._worker
        if worker is not None:
            worker.join(timeout=timeout)

    def is_idle(self):
        with self._cv:
            return not self._running and not self._pending


class SafeWriter:
    """Writes only regular files confined to a resolved, already-existing
    run directory. Rejects absolute paths, traversal, symlinked parents,
    symlink targets, non-regular targets, and hard-linked targets. Writes
    atomically via an exclusive restrictive temporary file, fsyncs file
    and directory, and maintains an exact allowed-write ledger (relative
    path, size, sha256). No production-write capability.
    """

    def __init__(self, run_dir):
        if os.path.islink(run_dir):
            raise ValueError("run_dir must not be a symlink")
        if not os.path.isdir(run_dir):
            raise ValueError("run_dir must already exist")
        self.run_dir = os.path.realpath(run_dir)
        self.ledger = []
        # Test-only hook to deterministically inject a replacement race.
        # Never used by production code paths.
        self._pre_replace_hook = None

    def _validate_no_symlink_parents(self, target):
        rel = os.path.relpath(target, self.run_dir)
        parts = rel.split(os.sep)
        current = self.run_dir
        for part in parts[:-1]:
            if part in ("", os.curdir):
                continue
            if part == os.pardir:
                raise ValueError("path traversal rejected")
            current = os.path.join(current, part)
            if os.path.lexists(current):
                if os.path.islink(current):
                    raise ValueError("symlink encountered in parent chain")
                if not os.path.isdir(current):
                    raise ValueError("parent path component is not a directory")
            else:
                os.mkdir(current, 0o700)
        return current

    def write_bytes(self, relative_path, data):
        if os.path.isabs(relative_path):
            raise ValueError("absolute paths are not allowed")
        norm = os.path.normpath(relative_path)
        if norm in (os.curdir,) or norm.startswith(os.pardir) or os.path.isabs(norm):
            raise ValueError("path traversal rejected")

        target = os.path.abspath(os.path.join(self.run_dir, norm))
        if not (target == self.run_dir or target.startswith(self.run_dir + os.sep)):
            raise ValueError("path escapes run directory")

        target_dir = self._validate_no_symlink_parents(target)
        real_target_dir = os.path.realpath(target_dir)
        if not (
            real_target_dir == self.run_dir
            or real_target_dir.startswith(self.run_dir + os.sep)
        ):
            raise ValueError("resolved parent escapes run directory")

        if os.path.lexists(target):
            lst = os.lstat(target)
            if stat.S_ISLNK(lst.st_mode):
                raise ValueError("target is a symlink")
            if not stat.S_ISREG(lst.st_mode):
                raise ValueError("target is not a regular file")
            if lst.st_nlink != 1:
                raise ValueError("target is a hard link")

        nofollow = getattr(os, "O_NOFOLLOW", 0)
        tmp_name = f".tmp-{secrets.token_hex(8)}"
        tmp_path = os.path.join(target_dir, tmp_name)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | nofollow
        fd = os.open(tmp_path, flags, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ValueError("temporary file is not regular")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())

            if self._pre_replace_hook is not None:
                self._pre_replace_hook(target, target_dir)

            if os.path.islink(target_dir) or os.path.realpath(target_dir) != real_target_dir:
                raise ValueError("target directory identity changed before replace")
            if os.path.lexists(target):
                lst2 = os.lstat(target)
                if stat.S_ISLNK(lst2.st_mode) or not stat.S_ISREG(lst2.st_mode):
                    raise ValueError("target was replaced with an unsafe object")
                if lst2.st_nlink != 1:
                    raise ValueError("target was replaced with a hard link")

            os.replace(tmp_path, target)
        except Exception:
            try:
                if os.path.lexists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass
            raise

        dir_fd = os.open(target_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        except Exception:
            pass
        finally:
            os.close(dir_fd)

        digest = hashlib.sha256(data).hexdigest()
        self.ledger.append(
            {"relative_path": norm, "size": len(data), "sha256": digest}
        )
        return target

    def write_text(self, relative_path, content, encoding="utf-8"):
        return self.write_bytes(relative_path, content.encode(encoding))


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/canonical_modules.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

```python
"""
sqlite_ownership.py (TASK 034)

Two independent capabilities live in this module:

1. The original structural (AST-based) transformation and verifier
   enforcing short SQLite ownership: SELECT rows are materialized into
   ordinary immutable values and the cursor/connection are closed
   BEFORE any slow-call category (formatting/hash/sleep/network/
   filesystem/Telegram I/O). Preserved unchanged for compatibility.

2. A new canonical, read-only, fail-closed SQLite evidence API used to
   prove UA-0009 row identity/ownership without ever emitting raw field
   values, names, phones, messages, blobs, or database pages. Only
   structural table/column identifiers, bounded row counts/identity
   hashes, and SHA-256 digests are returned.

No network access. No production paths. No writes. No migrations, WAL
changes, VACUUM, REINDEX, or mutable PRAGMAs are ever issued.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import stat
import sys
import urllib.parse
from dataclasses import dataclass, asdict
from typing import List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------
# Section 1: original AST-based short-ownership transform (unchanged
# public interface: AnchorNotFoundError, find_db_handle_names,
# verify_no_live_handle_across_slow_call, transform_short_ownership).
# --------------------------------------------------------------------

SLOW_CALL_NAMES = {
    "sleep", "time.sleep",
    "send_message", "send_photo", "send_video", "send_document",
    "reply_photo", "reply_video", "reply_text", "reply_document",
    "requests.get", "requests.post", "urlopen",
    "open", "write", "system", "run", "Popen", "call",
    "render", "generate", "build",
}


class AnchorNotFoundError(Exception):
    pass


def _iter_functions(tree: ast.AST, names: Set[str]):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            yield node


def _call_qualname(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = ""
        if isinstance(func.value, ast.Name):
            base = func.value.id + "."
        return base + func.attr
    return ""


def find_db_handle_names(func) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


def verify_no_live_handle_across_slow_call(func) -> List[str]:
    """Walk the statements of `func` in execution order (including simple
    nested blocks) and report violations where a DB handle name (or a
    cursor derived from it) is still open -- i.e. not yet closed -- at
    the point a slow call occurs. Conservative: anything that cannot be
    proven safe is reported as a violation.
    """
    handle_names = find_db_handle_names(func)
    if not handle_names:
        return []
    cursor_names: Set[str] = set()
    state = {"closed": False}
    violations: List[str] = []

    def walk_stmts(stmts):
        for stmt in stmts:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                qual = _call_qualname(stmt.value)
                if qual.endswith("cursor") and isinstance(stmt.value.func, ast.Attribute):
                    owner = getattr(stmt.value.func.value, "id", None)
                    if owner in handle_names:
                        for t in stmt.targets:
                            if isinstance(t, ast.Name):
                                cursor_names.add(t.id)
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    qual = _call_qualname(node)
                    owner = qual.split(".")[0] if "." in qual else None
                    if qual.endswith("close") and (owner in handle_names or owner in cursor_names):
                        state["closed"] = True
                    if any(qual == s or qual.endswith("." + s) or qual == s.split(".")[-1]
                           for s in SLOW_CALL_NAMES):
                        if not state["closed"]:
                            violations.append(
                                f"line {getattr(node, 'lineno', '?')}: slow call "
                                f"'{qual}' before DB handle close"
                            )
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                for field in ("body", "orelse", "finalbody"):
                    block = getattr(stmt, field, None)
                    if isinstance(block, list):
                        walk_stmts(block)
                handlers = getattr(stmt, "handlers", None)
                if handlers:
                    for h in handlers:
                        walk_stmts(h.body)

    walk_stmts(func.body)
    return violations


def _ensure_short_timeout(func, handle_names: Set[str]) -> None:
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                has_timeout = any(kw.arg == "timeout" for kw in node.value.keywords)
                if not has_timeout:
                    node.value.keywords.append(
                        ast.keyword(arg="timeout", value=ast.Constant(value=2))
                    )


def transform_short_ownership(source: str, function_names: Set[str]) -> str:
    """Rewrite the named functions so the sqlite3 connection/cursor is
    guaranteed closed (via try/finally) immediately after the last
    statement referencing the DB handle, before any subsequent
    formatting/slow work. Sets a short (2s) connect timeout if none is
    given. Raises AnchorNotFoundError if a function or its DB handle
    cannot be unambiguously identified.
    """
    tree = ast.parse(source)
    found = list(_iter_functions(tree, function_names))
    found_names = {f.name for f in found}
    missing = function_names - found_names
    if missing:
        raise AnchorNotFoundError(f"functions not found: {sorted(missing)}")

    for func in found:
        handle_names = find_db_handle_names(func)
        if not handle_names:
            raise AnchorNotFoundError(
                f"no sqlite3.connect anchor found in function {func.name}"
            )
        _ensure_short_timeout(func, handle_names)

        handle_stmt_indices = []
        for idx, stmt in enumerate(func.body):
            refs_handle = any(
                isinstance(n, ast.Name) and n.id in handle_names
                for n in ast.walk(stmt)
            )
            if refs_handle:
                handle_stmt_indices.append(idx)
        if not handle_stmt_indices:
            raise AnchorNotFoundError(
                f"DB handle {handle_names} unused after connect in {func.name}"
            )
        last_db_idx = max(handle_stmt_indices)
        db_block = func.body[: last_db_idx + 1]
        rest_block = func.body[last_db_idx + 1:]

        close_stmts = []
        for name in sorted(handle_names):
            close_call = ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id=name, ctx=ast.Load()),
                                        attr="close", ctx=ast.Load()),
                    args=[], keywords=[],
                )
            )
            close_stmts.append(close_call)

        try_node = ast.Try(body=db_block, handlers=[], orelse=[], finalbody=close_stmts)
        func.body = [try_node] + rest_block
        ast.fix_missing_locations(func)

    return ast.unparse(tree)


# --------------------------------------------------------------------
# Section 2: canonical read-only, fail-closed SQLite evidence API
# (TASK 034). Standard library only. Never raises for expected
# operational conditions (missing/locked/malformed/ambiguous/overflow);
# always returns a structured OwnershipEvidence with status OK/BLOCKED.
# --------------------------------------------------------------------

MAX_TABLES = 50
MAX_COLUMNS = 50
MAX_ROWS = 1000
MAX_SERIALIZED_BYTES = 1_000_000


@dataclass
class OwnershipEvidence:
    status: str  # "OK" or "BLOCKED"
    reason: str
    quick_check: Optional[str] = None
    query_only: Optional[int] = None
    table: Optional[str] = None
    row_count: Optional[int] = None
    rows_sha256: Optional[str] = None
    evidence_sha256: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _sanitize(exc: BaseException) -> str:
    # Only the exception class name is ever surfaced -- never the
    # message, which could embed a path or a fragment of data.
    return type(exc).__name__


def _validate_db_path(path: str):
    """Validate the database path with lstat: must be a regular,
    non-symlink file with a stable identity (nlink == 1). Fails closed
    on any hard-link surprise."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        return False, f"path_stat_failed:{_sanitize(exc)}"
    if stat.S_ISLNK(st.st_mode):
        return False, "path_is_symlink"
    if not stat.S_ISREG(st.st_mode):
        return False, "path_not_regular_file"
    if st.st_nlink != 1:
        return False, "path_hard_linked"
    return True, "ok"


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def collect_ua0009_ownership_evidence(
    db_path: str,
    table: str,
    id_column: str,
    id_value: str = "UA-0009",
    timeout: float = 2.0,
    max_tables: int = MAX_TABLES,
    max_columns: int = MAX_COLUMNS,
    max_rows: int = MAX_ROWS,
    max_serialized_bytes: int = MAX_SERIALIZED_BYTES,
) -> OwnershipEvidence:
    """Read-only, fail-closed evidence collection selecting exactly one
    row identified by the configured exact identifier-column rule
    (table/id_column/id_value). The cursor and connection are always
    closed BEFORE any hashing/serialization occurs. Never raises for
    expected operational conditions."""
    valid, reason = _validate_db_path(db_path)
    if not valid:
        return OwnershipEvidence(status="BLOCKED", reason=reason)

    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    quick_check_val = None
    query_only_val = None

    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    except sqlite3.Error as exc:
        return OwnershipEvidence(status="BLOCKED", reason=f"open_failed:{_sanitize(exc)}")

    rows = None
    try:
        try:
            cur = conn.cursor()
            try:
                cur.execute("PRAGMA query_only=ON")
                row = cur.execute("PRAGMA query_only").fetchone()
                query_only_val = row[0] if row else None

                row = cur.execute("PRAGMA quick_check").fetchone()
                quick_check_val = row[0] if row else None
                if quick_check_val != "ok":
                    return OwnershipEvidence(
                        status="BLOCKED", reason="quick_check_not_ok",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )

                tables = cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' LIMIT ?",
                    (max_tables + 1,),
                ).fetchall()
                if len(tables) > max_tables:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="table_overflow",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )
                table_names = {r[0] for r in tables}
                if table not in table_names:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="missing_table",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )

                columns = cur.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
                if len(columns) > max_columns:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="column_overflow",
                        quick_check=quick_check_val, query_only=query_only_val, table=table,
                    )
                column_names = {c[1] for c in columns}
                if id_column not in column_names:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="missing_column",
                        quick_check=quick_check_val, query_only=query_only_val, table=table,
                    )

                select_sql = (
                    f"SELECT rowid, * FROM {_quote_ident(table)} "
                    f"WHERE {_quote_ident(id_column)} = ? LIMIT ?"
                )
                rows = cur.execute(select_sql, (id_value, max_rows + 1)).fetchall()
            finally:
                cur.close()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return OwnershipEvidence(
            status="BLOCKED", reason=f"sqlite_error:{_sanitize(exc)}",
            quick_check=quick_check_val, query_only=query_only_val,
        )

    # Cursor and connection are now closed. Only materialized, immutable
    # values remain; hashing/serialization happens strictly below.
    if not rows:
        return OwnershipEvidence(
            status="BLOCKED", reason="missing_row",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )
    if len(rows) > 1:
        return OwnershipEvidence(
            status="BLOCKED", reason="ambiguous_row",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )

    serialized = repr(rows[0]).encode("utf-8")
    if len(serialized) > max_serialized_bytes:
        return OwnershipEvidence(
            status="BLOCKED", reason="serialized_overflow",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )
    row_hash = hashlib.sha256(serialized).hexdigest()
    combined = hashlib.sha256(
        f"{quick_check_val}|{query_only_val}|{table}|{id_column}|{row_hash}".encode("utf-8")
    ).hexdigest()

    return OwnershipEvidence(
        status="OK", reason="ok", quick_check=quick_check_val, query_only=query_only_val,
        table=table, row_count=1, rows_sha256=row_hash, evidence_sha256=combined,
    )


def compare_ownership_evidence(before: OwnershipEvidence, after: OwnershipEvidence):
    """Pure comparison helper for before/after UA-0009 evidence. OK only
    when both evidence objects are complete (status OK) and their
    evidence_sha256 hashes match exactly."""
    if before.status != "OK" or after.status != "OK":
        return False, "incomplete_evidence"
    if not before.evidence_sha256 or not after.evidence_sha256:
        return False, "incomplete_evidence"
    if before.evidence_sha256 != after.evidence_sha256:
        return False, "hash_mismatch"
    return True, "ok"


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

```python
"""CRM-SPEED-001 Gate A orchestration (TASK 032 canonical integration,
TASK 035 evidence integration).

This module provides one canonical evidence-computation core plus two
callers:

- run_gate_a(fixture): historical compatibility adapter for in-memory
  source fixtures (unit tests). It safely creates a requested
  non-existing run_dir after validating its parent, then delegates all
  predicate evaluation to the same _compute_evidence()/evaluate_gate_a()
  functions used by the canonical orchestrator. It does not retain a
  synthetic parallel evidence-evaluation path.

- orchestrate_gate_a(config, opener=None, clock=None): the real public
  orchestration entry point used by the no-argument launcher and by
  tests that inject a temporary filesystem configuration. It performs
  the full secure lifecycle described in TASK 032: Gate A lock
  acquisition, a validated QA root, atomic unique run-directory
  creation, secure source reads, isolated candidate/diff creation,
  compile-only verification (no import/execution of application
  modules), structural/concurrency/SQLite/publication evidence, and
  measured phase records (20/40/60/80/100).

Gate A is never executed against production by this repository. Every
function here operates only on paths/strings explicitly supplied by the
caller (production launcher DEFAULT_CONFIG or a test fixture/config).

TASK 035 integration: the canonical read-only SQLite ownership evidence
(sqlite_ownership.collect_ua0009_ownership_evidence /
compare_ownership_evidence) and the canonical no-redirect publication
probe (ua0009_publication_check.canonical_probe_ua0009) are used
directly by orchestrate_gate_a -- their logic is never duplicated here.
UA-0009 evidence is collected once before the candidate workload and
once after the entire workload, and compared through the canonical
helper; missing/non-OK/changed evidence always BLOCKS, never fabricated
as unchanged. When cars_ui semantic analysis blocks the transform
before compile-time evidence would otherwise exist, safe compile-only
evidence is still recorded from the exact secure original bytes
(candidate_origin=original_due_to_transform_block); this never permits
a final PASS by itself since the remaining structural predicates stay
missing/BLOCKED in that path.
"""
import os
import ast
import stat
import json
import time
import shutil
import secrets
import hashlib
import difflib
import sqlite3
import urllib.request
import urllib.error

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
import cars_ui_transform
import sqlite_ownership
import ua0009_publication_check

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_FILES_PER_ROOT = 32

ADMIN_ROUTE_NAMES = ["gallery", "video_gallery", "diag_photo_show", "diag_video_show"]

MEDIA_METHOD_NAMES = {
    "reply_photo", "reply_video", "reply_media_group", "reply_document",
    "reply_audio", "reply_voice", "reply_animation",
    "send_photo", "send_video", "send_media_group", "send_document",
    "send_audio", "send_voice", "send_animation",
    "download", "download_to_drive", "get_file",
}

DYNAMIC_DISPATCH_FORBIDDEN = {"getattr", "setattr", "eval", "exec", "globals", "locals"}

SAFE_BUILTIN_NAMES = {
    "str", "int", "float", "bool", "len", "print", "list", "dict", "set",
    "tuple", "sorted", "enumerate", "range", "isinstance", "format", "repr",
    "min", "max", "sum", "any", "all", "zip", "map", "filter",
}

ALLOWED_SITE_NAMES = (
    ["index.html", "katalog.html"]
    + [f"UA-000{n}.html" for n in range(1, 10)]
    + [f"UA-000{n}-diag.html" for n in range(1, 10)]
    + [f"UA-000{n}-track.html" for n in range(1, 10)]
)

DEFAULT_CONFIG = {
    "required_inputs": [
        "/home/Carix/.local/lib/python3.10/site-packages/usercustomize.py",
        "/home/Carix/.local/lib/python3.13/site-packages/usercustomize.py",
        "/home/Carix/start_safe.py",
        "/home/Carix/run_all.py",
        "/home/Carix/cars_ui.py",
        "/home/Carix/avtoperedacha.py",
        "/home/Carix/samokontrol.py",
        "/home/Carix/db.py",
        "/home/Carix/team_bot.py",
        "/home/Carix/stranica.py",
        "/home/Carix/crm.db",
    ],
    "site_roots": {
        "/home/Carix/site": ALLOWED_SITE_NAMES,
        "/home/Carix/video": ALLOWED_SITE_NAMES,
        "/home/Carix/public_html": ALLOWED_SITE_NAMES,
    },
    "ua0009_url": "https://ua-art-detailing.ru/UA-0009.html",
    "run_root": "/home/Carix/qa/crm_speed_task020",
    "backup_archive": "/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz",
    "backup_archive_sha256": "b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913",
    "protected_function_names": [],
    "db_function_source": None,
    "min_free_bytes": 10 * 1024 * 1024,
    # UA-0009 SQLite row-identity table/column configuration is
    # intentionally left unconfigured pending owner-verified schema
    # confirmation. Until configured, UA-0009 ownership evidence fails
    # closed (BLOCKED) rather than fabricating an unchanged result.
    "ua0009_table": None,
    "ua0009_id_column": None,
    "ua0009_id_value": "UA-0009",
}

REQUIRED_PREDICATES = [
    "inputs_present_and_regular",
    "backup_verified",
    "candidates_compile",
    "protected_fingerprints_unchanged",
    "sqlite_readonly_quickcheck_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_not_public",
    "site_inventory_unchanged",
    "admin_routes_text_only",
    "media_persistence_unchanged",
    "usercustomize_inert",
    "singleton_guard_present",
    "rebuild_queue_bound_no_process_spawn",
    "db_closed_before_slow_work",
    "deterministic_repeat_all_transforms",
    "no_production_write",
]


class _GateABlocked(Exception):
    """Raised internally to short-circuit an orchestration phase with a
    known reason. Always converted into a BLOCKED phase result."""


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_file(path):
    if not os.path.exists(path):
        return None
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return {"symlink": True}
    return {
        "mode": st.st_mode,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha256": _sha256_file(path),
    }


# ---------------------------------------------------------------------------
# Thin adapters around the canonical cars_ui_transform implementation
# ---------------------------------------------------------------------------

def _is_safe_builtin_unresolved(flag):
    if flag.startswith("unresolved_callable:"):
        parts = flag.split(":")
        name = parts[1] if len(parts) > 1 else ""
        return name in SAFE_BUILTIN_NAMES
    return False


def _translate_dynamic_flag(flag):
    if flag.startswith("getattr_dispatch"):
        return "dynamic_dispatch_forbidden:getattr"
    return flag


def scan_reachable_call_graph(source, entry_points, max_depth=25):
    tree = ast.parse(source)
    module_function_names = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    violations = []
    for ep in entry_points:
        if ep not in module_function_names:
            violations.append(f"missing_entry_point:{ep}")

    scan = cars_ui_transform.scan_reachable_call_graph(tree, entry_points)

    for func_name in sorted(scan.reachable):
        for flag in scan.unresolved_dynamic.get(func_name, []):
            if _is_safe_builtin_unresolved(flag):
                continue
            violations.append(_translate_dynamic_flag(flag))
        for call_info in scan.direct_media_calls.get(func_name, []):
            violations.append(f"direct_media_call:{call_info.method}")

    clean = len(violations) == 0
    return clean, violations


def generate_unified_diff(original, candidate):
    original = original or ""
    candidate = candidate or ""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        candidate.splitlines(keepends=True),
        fromfile="original", tofile="candidate",
    )
    return "".join(diff)


def transform_cars_ui(source, entry_points=None):
    entry_points = entry_points or ADMIN_ROUTE_NAMES
    try:
        clean_before, violations_before = scan_reachable_call_graph(source, entry_points)
    except SyntaxError as exc:
        return {"candidate": None, "status": "BLOCKED", "reasons": [f"syntax_error:{exc}"]}

    dynamic_flags = [v for v in violations_before if not v.startswith("direct_media_call")]
    if dynamic_flags:
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before}

    if not violations_before:
        return {"candidate": source, "status": "OK", "reasons": []}

    canonical_result = cars_ui_transform.transform_cars_ui(source, entry_points)
    if canonical_result.get("status") != "OK" or canonical_result.get("candidate") is None:
        reason = canonical_result.get("reason", "canonical_transform_blocked")
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before + [reason]}

    candidate = canonical_result["candidate"]
    clean_after, violations_after = scan_reachable_call_graph(candidate, entry_points)
    if not clean_after:
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before + violations_after}
    return {"candidate": candidate, "status": "OK", "reasons": violations_before}


def _stable_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def measure_deterministic_repeat(transform_fn, source, args=(), repeats=10):
    records = []
    for _ in range(repeats):
        result = transform_fn(source, *args)
        candidate = result.get("candidate")
        status = result.get("status")
        reasons = result.get("reasons", [])
        candidate_bytes = _stable_bytes(candidate)
        diff_text = generate_unified_diff(source, candidate)
        diff_bytes = diff_text.encode("utf-8")
        metadata_digest = hashlib.sha256(
            json.dumps({"status": status, "reasons": reasons}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        records.append({
            "candidate_sha256": _sha256_bytes(candidate_bytes),
            "diff_sha256": _sha256_bytes(diff_bytes),
            "status": status,
            "reasons": reasons,
            "metadata_digest": metadata_digest,
        })
    first = records[0]
    deterministic = all(r == first for r in records)
    return {"deterministic": deterministic, "repeats": repeats, "records": records}


def scan_bounded_inventory(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    if not os.path.isdir(root):
        return {"status": "BLOCKED", "reason": "missing_root", "root": root}
    matched = []
    for name in allowed_names:
        candidate_path = os.path.join(root, name)
        if os.path.lexists(candidate_path):
            matched.append(candidate_path)
    if len(matched) > max_files_per_root:
        return {
            "status": "BLOCKED", "reason": "overflow",
            "matched_count": len(matched), "max_files_per_root": max_files_per_root,
        }
    entries = []
    for path in matched:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            return {"status": "BLOCKED", "reason": "symlink_rejected", "path": path}
        if not stat.S_ISREG(st.st_mode):
            return {"status": "BLOCKED", "reason": "not_regular_file", "path": path}
        if st.st_nlink != 1:
            return {"status": "BLOCKED", "reason": "hard_link_rejected", "path": path}
        entries.append({
            "path": os.path.realpath(path),
            "mode": st.st_mode,
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": _sha256_file(path),
        })
    entries.sort(key=lambda e: e["path"])
    return {"status": "OK", "entries": entries, "matched_count": len(matched), "max_files_per_root": max_files_per_root}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_ua0009_not_public(url, opener=None):
    """Historical fixture-facing adapter, preserved unchanged for
    _compute_evidence()/run_gate_a() compatibility. orchestrate_gate_a()
    uses the canonical ua0009_publication_check.canonical_probe_ua0009
    directly instead (see phase80 below) rather than this adapter."""
    if not url or not url.startswith("https://"):
        return {"status": "BLOCKED", "reason": "missing_or_non_https_url"}
    if opener is None:
        opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        req = urllib.request.Request(url, method="GET")
        resp = opener.open(req, timeout=5)
        code = getattr(resp, "getcode", lambda: getattr(resp, "code", None))()
        return {"status": "BLOCKED", "reason": f"unexpected_status_{code}"}
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return {"status": "OK", "reason": f"not_served_{exc.code}", "http_status": exc.code}
        return {"status": "BLOCKED", "reason": f"http_error_{exc.code}"}
    except urllib.error.URLError as exc:
        return {"status": "BLOCKED", "reason": f"network_error:{exc.reason}"}
    except Exception as exc:
        return {"status": "BLOCKED", "reason": f"probe_exception:{type(exc).__name__}"}


def check_inputs_present_and_regular(paths):
    missing = []
    for p in paths:
        if not os.path.exists(p):
            missing.append(p)
            continue
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            missing.append(p)
    if missing:
        return {"status": "BLOCKED", "missing_or_symlink": missing}
    return {"status": "OK", "checked": paths}


def check_backup_verified(archive_path, expected_sha256):
    if not os.path.exists(archive_path):
        return {"status": "BLOCKED", "reason": "backup_missing"}
    actual = _sha256_file(archive_path)
    if actual != expected_sha256:
        return {"status": "BLOCKED", "reason": "backup_hash_mismatch"}
    return {"status": "OK", "sha256": actual}


def check_candidates_compile(candidate_sources):
    errors = {}
    for name, src in candidate_sources.items():
        try:
            compile(src, name, "exec")
        except SyntaxError as exc:
            errors[name] = str(exc)
    if errors:
        return {"status": "BLOCKED", "errors": errors}
    return {"status": "OK", "compiled": list(candidate_sources.keys())}


def check_protected_fingerprints_unchanged(before, after):
    if not before or not after:
        return {"status": "BLOCKED", "reason": "missing_fingerprints"}
    if before != after:
        diff_keys = [k for k in before if before.get(k) != after.get(k)]
        return {"status": "BLOCKED", "reason": "changed", "diff_keys": diff_keys}
    return {"status": "OK"}


def check_sqlite_readonly_quickcheck_ok(db_path):
    if not os.path.exists(db_path):
        return {"status": "BLOCKED", "reason": "db_missing"}
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=ON;")
            cur = conn.execute("PRAGMA quick_check;")
            result = cur.fetchone()
        finally:
            conn.close()
        if result and result[0] == "ok":
            return {"status": "OK", "quick_check": result[0]}
        return {"status": "BLOCKED", "reason": "quick_check_failed", "value": result}
    except sqlite3.OperationalError as exc:
        return {"status": "BLOCKED", "reason": f"sqlite_locked_or_error:{exc}"}


def check_admin_routes_text_only(cars_ui_source):
    result = transform_cars_ui(cars_ui_source)
    if result["status"] != "OK" or result["candidate"] is None:
        return {"status": "BLOCKED", "reasons": result["reasons"]}
    clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
    if not clean:
        return {"status": "BLOCKED", "reasons": violations}
    return {"status": "OK", "candidate_sha256": _sha256_bytes(result["candidate"].encode("utf-8"))}


def _extract_function_ast_dumps(source, names):
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            found[node.name] = ast.dump(node)
    return found


def check_media_persistence_unchanged(original_source, candidate_source, protected_function_names):
    before = _extract_function_ast_dumps(original_source, protected_function_names)
    after = _extract_function_ast_dumps(candidate_source or "", protected_function_names)
    missing = [n for n in protected_function_names if n not in after]
    if missing:
        return {"status": "BLOCKED", "reason": "missing_protected_functions", "missing": missing}
    changed = [n for n in protected_function_names if before.get(n) != after.get(n)]
    if changed:
        return {"status": "BLOCKED", "reason": "protected_functions_changed", "changed": changed}
    return {"status": "OK"}


FORBIDDEN_USERCUSTOMIZE_MODULES = {
    "team_bot", "run_all", "start_safe", "avtoperedacha", "stranica",
    "threading", "multiprocessing", "subprocess",
}


def check_usercustomize_inert(source):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    violations = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_USERCUSTOMIZE_MODULES:
                    violations.append(f"forbidden_import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_USERCUSTOMIZE_MODULES:
                violations.append(f"forbidden_import_from:{node.module}")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            violations.append("top_level_call_statement")
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


def check_singleton_guard_present(tmp_dir):
    lock_path = os.path.join(tmp_dir, "singleton.lock")
    guard1 = SingletonGuard(lock_path)
    ok1 = guard1.acquire()
    guard2 = SingletonGuard(lock_path)
    ok2 = guard2.acquire()
    guard1.release()
    guard3 = SingletonGuard(lock_path)
    ok3 = guard3.acquire()
    guard3.release()
    if ok1 and not ok2 and ok3:
        return {"status": "OK"}
    return {"status": "BLOCKED", "reason": "singleton_semantics_violated", "ok1": ok1, "ok2": ok2, "ok3": ok3}


def check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source):
    try:
        tree = ast.parse(avtoperedacha_source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "multiprocessing"):
                    violations.append(f"forbidden_import:{alias.name}")
        if isinstance(node, ast.Attribute) and node.attr in ("system", "Popen", "call", "run", "check_call", "check_output"):
            violations.append(f"forbidden_call_site:{node.attr}")
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


SLOW_CALL_NAMES = {"sleep", "send_message", "send_photo", "render", "generate", "post", "request"}


def check_db_closed_before_slow_work(function_source):
    try:
        tree = ast.parse(function_source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node
            break
    if func is None:
        return {"status": "BLOCKED", "reason": "no_function_found"}
    close_index = None
    slow_index = None
    for i, stmt in enumerate(func.body):
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "close" and close_index is None:
                    close_index = i
                if node.func.attr in SLOW_CALL_NAMES and slow_index is None:
                    slow_index = i
    if close_index is None:
        return {"status": "BLOCKED", "reason": "no_close_found"}
    if slow_index is not None and slow_index < close_index:
        return {"status": "BLOCKED", "reason": "slow_work_before_close"}
    return {"status": "OK", "close_index": close_index, "slow_index": slow_index}


def check_deterministic_repeat_all_transforms(transform_map):
    failures = []
    for name, (fn, source, args) in transform_map.items():
        measurement = measure_deterministic_repeat(fn, source, args=args, repeats=10)
        if not measurement["deterministic"]:
            failures.append(name)
    if failures:
        return {"status": "BLOCKED", "failures": failures}
    return {"status": "OK", "checked": list(transform_map.keys())}


def check_site_inventory_unchanged(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    before = scan_bounded_inventory(root, allowed_names, max_files_per_root)
    after = scan_bounded_inventory(root, allowed_names, max_files_per_root)
    if before.get("status") != "OK" or after.get("status") != "OK":
        return {"status": "BLOCKED", "before": before, "after": after}
    if before["entries"] != after["entries"]:
        return {"status": "BLOCKED", "reason": "inventory_changed"}
    return {"status": "OK", "matched_count": before["matched_count"]}


def check_no_production_write(protected_before, protected_after, site_before, site_after):
    if protected_before != protected_after:
        return {"status": "BLOCKED", "reason": "protected_changed"}
    if site_before != site_after:
        return {"status": "BLOCKED", "reason": "site_inventory_changed"}
    return {"status": "OK"}


def _collect_ua0009_sqlite_evidence(config, db_path):
    """Delegates entirely to sqlite_ownership.collect_ua0009_ownership_evidence
    (the exact canonical implementation) -- no duplicated logic. Missing
    table/column/db configuration fails closed (BLOCKED), never
    fabricated."""
    table = config.get("ua0009_table")
    id_column = config.get("ua0009_id_column")
    id_value = config.get("ua0009_id_value", "UA-0009")
    if not db_path or not table or not id_column:
        return sqlite_ownership.OwnershipEvidence(
            status="BLOCKED", reason="ua0009_table_or_column_not_configured"
        )
    return sqlite_ownership.collect_ua0009_ownership_evidence(db_path, table, id_column, id_value)


def evaluate_gate_a(evidence):
    unmet = []
    for key in REQUIRED_PREDICATES:
        item = evidence.get(key)
        if not isinstance(item, dict) or item.get("status") != "OK":
            unmet.append(key)
    if unmet:
        return "BLOCKED", unmet
    return "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", []


# ---------------------------------------------------------------------------
# Canonical evidence computation shared by run_gate_a() and
# orchestrate_gate_a()
# ---------------------------------------------------------------------------

def _compute_evidence(fixture):
    evidence = {}
    evidence["inputs_present_and_regular"] = check_inputs_present_and_regular(fixture["required_inputs"])
    evidence["backup_verified"] = check_backup_verified(fixture["backup_archive"], fixture["backup_archive_sha256"])

    cars_ui_candidate = transform_cars_ui(fixture["cars_ui_source"])
    usercustomize_source = fixture["usercustomize_source"]
    avtoperedacha_source = fixture["avtoperedacha_source"]

    candidate_sources = {
        "cars_ui.py": cars_ui_candidate.get("candidate") or fixture["cars_ui_source"],
        "usercustomize.py": usercustomize_source,
        "avtoperedacha.py": avtoperedacha_source,
    }
    evidence["candidates_compile"] = check_candidates_compile(candidate_sources)

    evidence["protected_fingerprints_unchanged"] = check_protected_fingerprints_unchanged(
        fixture["protected_fingerprints_before"], fixture["protected_fingerprints_after"])
    evidence["sqlite_readonly_quickcheck_ok"] = check_sqlite_readonly_quickcheck_ok(fixture["db_path"])
    evidence["ua0009_fingerprint_unchanged"] = check_protected_fingerprints_unchanged(
        fixture["ua0009_fingerprint_before"], fixture["ua0009_fingerprint_after"])
    evidence["ua0009_not_public"] = check_ua0009_not_public(fixture["ua0009_url"], fixture.get("ua0009_opener"))
    evidence["site_inventory_unchanged"] = check_site_inventory_unchanged(
        fixture["site_root"], fixture["allowed_site_names"], fixture.get("max_files_per_root", DEFAULT_MAX_FILES_PER_ROOT))
    evidence["admin_routes_text_only"] = check_admin_routes_text_only(fixture["cars_ui_source"])
    evidence["media_persistence_unchanged"] = check_media_persistence_unchanged(
        fixture["cars_ui_source"], cars_ui_candidate.get("candidate"), fixture["protected_function_names"])
    evidence["usercustomize_inert"] = check_usercustomize_inert(usercustomize_source)
    evidence["singleton_guard_present"] = check_singleton_guard_present(fixture["tmp_dir"])
    evidence["rebuild_queue_bound_no_process_spawn"] = check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source)
    evidence["db_closed_before_slow_work"] = check_db_closed_before_slow_work(fixture["db_function_source"])
    evidence["deterministic_repeat_all_transforms"] = check_deterministic_repeat_all_transforms({
        "cars_ui": (transform_cars_ui, fixture["cars_ui_source"], ()),
    })
    evidence["no_production_write"] = check_no_production_write(
        fixture["protected_fingerprints_before"], fixture["protected_fingerprints_after"],
        fixture.get("site_before"), fixture.get("site_after"))
    return evidence


def _ensure_run_dir(run_dir):
    """Safely create a requested non-existing run_dir after validating
    its parent. Never weakens SafeWriter: SafeWriter still refuses any
    directory that does not already exist by the time it is
    constructed."""
    parent = os.path.dirname(os.path.abspath(run_dir))
    if parent == "":
        parent = "."
    if not os.path.isdir(parent):
        raise ValueError(f"run_dir parent does not exist: {parent}")
    if os.path.islink(parent):
        raise ValueError("run_dir parent must not be a symlink")
    if os.path.islink(run_dir):
        raise ValueError("run_dir must not be a symlink")
    if not os.path.exists(run_dir):
        os.mkdir(run_dir, 0o700)
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir must be a directory")


def run_gate_a(fixture):
    """Historical compatibility adapter for in-memory source fixtures.
    Delegates all predicate evaluation to _compute_evidence() and
    evaluate_gate_a(), the exact same functions used by
    orchestrate_gate_a(). The only adapter-specific behavior is safely
    creating a requested non-existing run_dir after validating its
    parent, so SafeWriter always receives an already-existing directory.
    """
    evidence = _compute_evidence(fixture)
    status, unmet = evaluate_gate_a(evidence)
    receipt = {
        "status": status,
        "unmet_predicates": unmet,
        "evidence": evidence,
        "production_write": "NO",
        "pii_emitted": "NO",
        "generated_at": time.time(),
    }
    run_dir = fixture.get("run_dir")
    if run_dir:
        _ensure_run_dir(run_dir)
        writer = SafeWriter(run_dir)
        writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
    return receipt


# ---------------------------------------------------------------------------
# Canonical real orchestration entry point
# ---------------------------------------------------------------------------

def _validate_no_symlink_dir(path):
    if not os.path.isdir(path):
        raise _GateABlocked(f"qa_root_missing_or_not_dir:{path}")
    if os.path.islink(path):
        raise _GateABlocked("qa_root_is_symlink")
    abs_path = os.path.abspath(path)
    cur = ""
    for part in abs_path.split(os.sep):
        if not part:
            if not cur:
                cur = os.sep
            continue
        cur = os.path.join(cur, part) if cur else part
        if os.path.islink(cur):
            raise _GateABlocked(f"symlink_component:{cur}")
    return os.path.realpath(path)


def _create_unique_run_dir(qa_root_real):
    for _ in range(5):
        run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(6)
        candidate = os.path.join(qa_root_real, run_id)
        try:
            os.mkdir(candidate, 0o700)
        except FileExistsError:
            continue
        if os.path.islink(candidate):
            raise _GateABlocked("run_dir_became_symlink")
        parent_real = os.path.realpath(os.path.dirname(candidate))
        if parent_real != qa_root_real:
            raise _GateABlocked("run_dir_parent_identity_mismatch")
        if os.path.realpath(candidate) != candidate:
            raise _GateABlocked("run_dir_identity_mismatch")
        return candidate
    raise _GateABlocked("could_not_create_unique_run_dir")


def secure_read_file(path):
    try:
        lst = os.lstat(path)
    except FileNotFoundError:
        raise _GateABlocked(f"missing_input:{path}")
    if stat.S_ISLNK(lst.st_mode):
        raise _GateABlocked(f"symlink_input:{path}")
    if not stat.S_ISREG(lst.st_mode):
        raise _GateABlocked(f"non_regular_input:{path}")
    if lst.st_nlink != 1:
        raise _GateABlocked(f"hard_linked_input:{path}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, os.O_RDONLY | nofollow)
    except OSError as exc:
        raise _GateABlocked(f"open_failed:{path}:{type(exc).__name__}")
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or fst.st_nlink != 1:
            raise _GateABlocked(f"identity_changed_after_open:{path}")
        if fst.st_ino != lst.st_ino or fst.st_dev != lst.st_dev:
            raise _GateABlocked(f"identity_mismatch:{path}")
        with os.fdopen(fd, "rb", closefd=True) as fh:
            data = fh.read()
    except _GateABlocked:
        try:
            os.close(fd)
        except Exception:
            pass
        raise
    lst2 = os.lstat(path)
    if stat.S_ISLNK(lst2.st_mode) or not stat.S_ISREG(lst2.st_mode) or lst2.st_nlink != 1:
        raise _GateABlocked(f"identity_changed_after_read:{path}")
    return {
        "path": os.path.realpath(path),
        "size": len(data),
        "mode": lst.st_mode,
        "mtime_ns": lst.st_mtime_ns,
        "sha256": _sha256_bytes(data),
        "data": data,
    }


def _find_input_path(config, filename):
    for p in config.get("required_inputs", []):
        if os.path.basename(p) == filename:
            return p
    return None


def _render_report(receipt):
    lines = []
    lines.append("# Gate A Report - " + str(receipt.get("task_id")))
    lines.append("Status: " + str(receipt.get("status")))
    lines.append("Run ID: " + str(receipt.get("run_id")))
    lines.append("Generated at: " + str(receipt.get("generated_at")))
    lines.append("")
    lines.append("## Phases")
    for p in receipt.get("phases", []):
        lines.append(
            "- phase " + str(p.get("phase")) + " (" + str(p.get("label")) + "): "
            + str(p.get("status")) + " duration=" + str(p.get("duration")) + "s"
        )
    lines.append("")
    lines.append("## Unmet predicates")
    for u in receipt.get("unmet_predicates", []) or []:
        lines.append("- " + str(u))
    lines.append("")
    lines.append("## Blockers")
    for b in receipt.get("blockers", []) or []:
        lines.append("- " + str(b))
    lines.append("")
    lines.append("PRODUCTION_WRITE: " + str(receipt.get("production_write")))
    lines.append("Next safe action: " + str(receipt.get("next_safe_action")))
    return os.linesep.join(lines) + os.linesep


def orchestrate_gate_a(config, opener=None, clock=None):
    """The single, real, public orchestration entry point. Used by both
    the no-argument launcher (with DEFAULT_CONFIG) and by tests (with an
    injected temporary-directory configuration and an injected fake
    HTTPS opener). Never scans an account recursively; only reads the
    exact bounded paths present in `config`.

    TASK 035: read-only UA-0009 SQLite ownership evidence is collected
    once before the candidate workload (end of phase20) and once again
    only after the entire workload (start of phase100), always via the
    canonical sqlite_ownership.collect_ua0009_ownership_evidence /
    compare_ownership_evidence functions -- never duplicated here. The
    publication probe in phase80 delegates directly to the canonical
    ua0009_publication_check.canonical_probe_ua0009 with the injected
    opener.
    """
    clock = clock or time.monotonic
    phases = []
    evidence = {}
    site_before = {}
    site_after = {}
    candidate_sources = {}
    input_records = {}
    state = {"blocked": False}
    sqlite_state = {"before": None, "after": None}
    run_dir = None
    lock = None

    def run_phase(num, label, fn):
        start = clock()
        try:
            fn()
            outcome = "OK"
        except _GateABlocked as exc:
            evidence.setdefault("_blockers", []).append(str(exc))
            outcome = "BLOCKED"
        except Exception as exc:
            evidence.setdefault("_blockers", []).append(f"exception:{type(exc).__name__}:{exc}")
            outcome = "BLOCKED"
        end = clock()
        status_field = "finished" if num == 100 else outcome
        phases.append({
            "phase": num, "label": label, "start": start, "end": end,
            "duration": end - start, "status": status_field,
        })
        return outcome

    def phase20():
        nonlocal run_dir, lock
        qa_root_real = _validate_no_symlink_dir(config["run_root"])
        lock = CrossProcessLock(os.path.join(qa_root_real, "gate_a.lock"))
        if not lock.acquire():
            raise _GateABlocked("gate_a_lock_held")
        run_dir = _create_unique_run_dir(qa_root_real)
        for p in config["required_inputs"]:
            input_records[p] = secure_read_file(p)
        evidence["inputs_present_and_regular"] = {"status": "OK", "checked": list(input_records.keys())}
        du = shutil.disk_usage(qa_root_real)
        if du.free < config.get("min_free_bytes", 10 * 1024 * 1024):
            raise _GateABlocked("insufficient_free_space")
        backup_result = check_backup_verified(config["backup_archive"], config["backup_archive_sha256"])
        evidence["backup_verified"] = backup_result
        if backup_result["status"] != "OK":
            raise _GateABlocked("backup_verification_failed")
        evidence["_fingerprints_before"] = {p: fingerprint_file(p) for p in config["required_inputs"]}

        # Canonical, read-only, fail-closed UA-0009 SQLite ownership
        # evidence, collected once here (before the candidate workload).
        # Delegates entirely to sqlite_ownership; database resources are
        # closed internally before returning, i.e. strictly before any
        # transform/hashing/HTTP/filesystem work below.
        db_path = _find_input_path(config, "crm.db")
        sqlite_state["before"] = _collect_ua0009_sqlite_evidence(config, db_path)

        for root, names in config["site_roots"].items():
            site_before[root] = scan_bounded_inventory(root, names)

    def phase40():
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        cars_ui_path = _find_input_path(config, "cars_ui.py")
        usercustomize_path = _find_input_path(config, "usercustomize.py")
        avtoperedacha_path = _find_input_path(config, "avtoperedacha.py")
        if not (cars_ui_path and usercustomize_path and avtoperedacha_path):
            raise _GateABlocked("missing_source_paths_for_transform")
        cars_ui_source = input_records[cars_ui_path]["data"].decode("utf-8")
        usercustomize_source = input_records[usercustomize_path]["data"].decode("utf-8")
        avtoperedacha_source = input_records[avtoperedacha_path]["data"].decode("utf-8")
        evidence["_cars_ui_source"] = cars_ui_source
        evidence["_usercustomize_source"] = usercustomize_source
        evidence["_avtoperedacha_source"] = avtoperedacha_source

        result = transform_cars_ui(cars_ui_source)
        evidence["_transform_result"] = result
        if result["status"] != "OK" or result.get("candidate") is None:
            # Semantic transform blocked before a candidate could be
            # created. Still record safe compile-only evidence from the
            # exact secure original bytes (never executed/imported).
            # This is explicitly NOT an accepted candidate and never by
            # itself permits a final PASS -- the remaining structural
            # predicates (admin_routes_text_only, media_persistence,
            # etc.) stay missing/BLOCKED because phase80 is skipped.
            compile_map = {
                "cars_ui.py": cars_ui_source,
                "usercustomize.py": usercustomize_source,
                "avtoperedacha.py": avtoperedacha_source,
            }
            try:
                compile_result = check_candidates_compile(compile_map)
            except Exception as exc:
                compile_result = {"status": "BLOCKED", "reason": f"exception:{type(exc).__name__}"}
            if compile_result.get("status") == "OK":
                evidence["candidates_compile"] = {
                    "status": "OK",
                    "candidate_origin": "original_due_to_transform_block",
                    "compiled": compile_result.get("compiled", []),
                }
            else:
                evidence["candidates_compile"] = dict(
                    compile_result, candidate_origin="original_due_to_transform_block"
                )
            raise _GateABlocked("cars_ui_transform_blocked")

        candidate_sources["cars_ui.py"] = result["candidate"]
        candidate_sources["usercustomize.py"] = usercustomize_source
        candidate_sources["avtoperedacha.py"] = avtoperedacha_source
        diff_text = generate_unified_diff(cars_ui_source, candidate_sources["cars_ui.py"])
        evidence["_diff_sha256"] = _sha256_bytes(diff_text.encode("utf-8"))
        evidence["_candidate_hashes"] = {k: _sha256_bytes(v.encode("utf-8")) for k, v in candidate_sources.items()}

    def phase60():
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        if not candidate_sources:
            raise _GateABlocked("no_candidates_to_compile")
        result = check_candidates_compile(candidate_sources)
        evidence["candidates_compile"] = result
        if result["status"] != "OK":
            raise _GateABlocked("compile_failed")

    def phase80():
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        cars_ui_source = evidence.get("_cars_ui_source")
        candidate = candidate_sources.get("cars_ui.py")
        usercustomize_source = evidence.get("_usercustomize_source")
        avtoperedacha_source = evidence.get("_avtoperedacha_source")

        evidence["admin_routes_text_only"] = check_admin_routes_text_only(cars_ui_source)

        protected_names = config.get("protected_function_names") or []
        if not protected_names:
            evidence["media_persistence_unchanged"] = {"status": "BLOCKED", "reason": "protected_function_names_not_configured"}
        else:
            evidence["media_persistence_unchanged"] = check_media_persistence_unchanged(cars_ui_source, candidate, protected_names)

        evidence["usercustomize_inert"] = check_usercustomize_inert(usercustomize_source)
        evidence["singleton_guard_present"] = check_singleton_guard_present(run_dir)
        evidence["rebuild_queue_bound_no_process_spawn"] = check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source)

        db_path = _find_input_path(config, "crm.db")
        if db_path:
            evidence["sqlite_readonly_quickcheck_ok"] = check_sqlite_readonly_quickcheck_ok(db_path)
        else:
            evidence["sqlite_readonly_quickcheck_ok"] = {"status": "BLOCKED", "reason": "db_path_not_configured"}

        db_function_source = config.get("db_function_source")
        if db_function_source:
            evidence["db_closed_before_slow_work"] = check_db_closed_before_slow_work(db_function_source)
        else:
            evidence["db_closed_before_slow_work"] = {"status": "BLOCKED", "reason": "db_function_source_not_configured"}

        evidence["deterministic_repeat_all_transforms"] = check_deterministic_repeat_all_transforms({
            "cars_ui": (transform_cars_ui, cars_ui_source, ()),
        })

        # Delegate the publication probe directly to the canonical
        # no-redirect implementation with the injected opener -- no
        # duplicated HTTP logic here.
        publication_result = ua0009_publication_check.canonical_probe_ua0009(config["ua0009_url"], opener=opener)
        evidence["ua0009_not_public"] = {
            "status": "OK" if publication_result.status == "PASS" else "BLOCKED",
            "reason": publication_result.reason,
            "http_status": publication_result.status_code,
        }

        required_here = [
            "admin_routes_text_only", "media_persistence_unchanged", "usercustomize_inert",
            "singleton_guard_present", "rebuild_queue_bound_no_process_spawn",
            "sqlite_readonly_quickcheck_ok", "db_closed_before_slow_work",
            "deterministic_repeat_all_transforms", "ua0009_not_public",
        ]
        failed = [k for k in required_here if evidence.get(k, {}).get("status") != "OK"]
        if failed:
            raise _GateABlocked("predicate_failed:" + ",".join(failed))

    def phase100():
        fingerprints_after = {p: fingerprint_file(p) for p in config["required_inputs"]}
        evidence["_fingerprints_after"] = fingerprints_after
        fingerprints_before = evidence.get("_fingerprints_before")
        if fingerprints_before:
            evidence["protected_fingerprints_unchanged"] = check_protected_fingerprints_unchanged(fingerprints_before, fingerprints_after)
        else:
            evidence["protected_fingerprints_unchanged"] = {"status": "BLOCKED", "reason": "missing_before_fingerprints"}
        for root, names in config["site_roots"].items():
            try:
                site_after[root] = scan_bounded_inventory(root, names)
            except Exception as exc:
                site_after[root] = {"status": "BLOCKED", "reason": f"exception:{type(exc).__name__}"}
        site_ok = True
        changed_roots = []
        for root in config["site_roots"]:
            b = site_before.get(root)
            a = site_after.get(root)
            if not b or b.get("status") != "OK" or not a or a.get("status") != "OK" or b.get("entries") != a.get("entries"):
                site_ok = False
                changed_roots.append(root)
        evidence["site_inventory_unchanged"] = {"status": "OK"} if site_ok else {"status": "BLOCKED", "changed_roots": changed_roots}

        # Canonical UA-0009 SQLite ownership evidence, collected again
        # only after the entire workload (phases 20/40/60/80 have all
        # run or been skipped/blocked). Compared through the canonical
        # compare_ownership_evidence helper; missing, non-OK, or changed
        # evidence always BLOCKS -- never fabricated as unchanged.
        db_path = _find_input_path(config, "crm.db")
        before_ev = sqlite_state["before"] or sqlite_ownership.OwnershipEvidence(
            status="BLOCKED", reason="not_collected_before_block"
        )
        after_ev = _collect_ua0009_sqlite_evidence(config, db_path)
        sqlite_state["before"] = before_ev
        sqlite_state["after"] = after_ev
        cmp_ok, cmp_reason = sqlite_ownership.compare_ownership_evidence(before_ev, after_ev)
        evidence["ua0009_fingerprint_unchanged"] = {"status": "OK" if cmp_ok else "BLOCKED", "reason": cmp_reason}
        evidence["_sqlite_ownership_before"] = before_ev.to_dict()
        evidence["_sqlite_ownership_after"] = after_ev.to_dict()

        evidence["no_production_write"] = check_no_production_write(
            evidence.get("_fingerprints_before") or {}, fingerprints_after, site_before, site_after)

    try:
        outcome = run_phase(20, "lock_preflight_backup_fingerprints_sqlite_before", phase20)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(40, "secure_source_reads_and_candidate_diff", phase40)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(60, "compile_candidates", phase60)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(80, "structural_concurrency_sqlite_media_publication", phase80)
        if outcome != "OK":
            state["blocked"] = True
        run_phase(100, "finalization_fingerprints_inventories_sqlite_after_receipt", phase100)

        public_evidence = {k: v for k, v in evidence.items() if not k.startswith("_")}
        status, unmet = evaluate_gate_a(public_evidence)

        receipt = {
            "task_id": "CRM-SPEED-001",
            "run_id": os.path.basename(run_dir) if run_dir else None,
            "generated_at": time.time(),
            "phases": phases,
            "status": status,
            "unmet_predicates": unmet,
            "evidence": public_evidence,
            "package_hashes": evidence.get("_candidate_hashes", {}),
            "diff_sha256": evidence.get("_diff_sha256"),
            "site_inventories": {"before": site_before, "after": site_after},
            "sqlite_ownership": {
                "before": evidence.get("_sqlite_ownership_before"),
                "after": evidence.get("_sqlite_ownership_after"),
            },
            "publication_result": public_evidence.get("ua0009_not_public"),
            "synthetic_latency": {"non_production": True, "value_ms": 0},
            "blockers": evidence.get("_blockers", []),
            "allowed_write_ledger": [],
            "next_safe_action": (
                "await_task_033_real_evidence_then_owner_gate_b_review"
                if status == "BLOCKED" else
                "await_owner_gate_b_approval"
            ),
            "production_write": "NO",
            "pii_emitted": "NO",
        }

        if run_dir is not None:
            try:
                writer = SafeWriter(run_dir)
                writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
                writer.write_text("report.md", _render_report(receipt))
                receipt["allowed_write_ledger"] = writer.ledger
                writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
            except Exception as exc:
                receipt.setdefault("blockers", []).append(f"receipt_write_failed:{type(exc).__name__}")
        return receipt
    finally:
        if lock is not None:
            lock.release()


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/cars_ui_transform.py

```python
'''
CRM-SPEED-001 admin-media transform utilities.

Rewrites direct Telegram media-send calls (reply_photo, reply_video,
send_photo, send_video, reply_document, send_document,
reply_media_group, send_media_group) that are structurally direct and
reachable only from the fixed admin "cars UI" entry routes into
lightweight text-only replies.

Correction applied under TASK 027 (root cause from controller run on
commit 6e0ddb846f88eb4d36d0df36b69ed7f8b4fc437e):

The previous pre-scan descended into the argument subtree of an
already-recognized direct media-send call and separately reported the
media arguments (for example open('x.jpg','rb')) as an
unresolved_callable, which made transform_cars_ui BLOCK before the
whole media-send expression could be atomically replaced. This module
now treats a structurally direct media-send call as a single atomic
unit: its target/callee shape is inspected and blocked if dynamic, but
calls strictly inside its own argument subtree are not treated as
independently reachable runtime once the whole expression is replaced,
unless they are not on the small safe-to-drop allowlist
(open/download/thumbnail), in which case the whole call is left
unrewritten and blocked to avoid silently discarding side effects.

Any open()/download() call located outside such a removed expression is
still treated as a normal unresolved call and still blocks, exactly as
before this correction.

TASK 029: this module is the single canonical admin-media transform
implementation for CRM-SPEED-001. crm_speed_gate_a.py delegates to this
module via thin adapters instead of redefining transform/scan logic.
'''

import ast
import copy
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

MEDIA_METHODS = {
    'reply_photo',
    'reply_video',
    'send_photo',
    'send_video',
    'reply_document',
    'send_document',
    'reply_media_group',
    'send_media_group',
}

_TEXT_METHOD_MAP = {
    'reply_photo': 'reply_text',
    'reply_video': 'reply_text',
    'reply_document': 'reply_text',
    'reply_media_group': 'reply_text',
    'send_photo': 'send_message',
    'send_video': 'send_message',
    'send_document': 'send_message',
    'send_media_group': 'send_message',
}

_MEDIA_KIND = {
    'reply_photo': 'photo',
    'send_photo': 'photo',
    'reply_video': 'video',
    'send_video': 'video',
    'reply_document': 'document',
    'send_document': 'document',
    'reply_media_group': 'media group',
    'send_media_group': 'media group',
}

_SAFE_ARG_CALL_PATTERNS = ('open', 'download', 'thumbnail')

DEFAULT_ADMIN_ENTRY_ROUTES = (
    'admin_car_view',
    'admin_car_list',
    'admin_car_edit',
    'admin_car_delete',
)


@dataclass
class MediaCallInfo:
    func_name: str
    node: ast.Call
    stmt: ast.stmt
    method: str
    is_await: bool
    lineno: int


@dataclass
class ScanResult:
    call_graph: Dict[str, Set[str]]
    reverse_callers: Dict[str, Set[str]]
    reachable: Set[str]
    direct_media_calls: Dict[str, List[MediaCallInfo]]
    unresolved_dynamic: Dict[str, List[str]]
    functions: Dict[str, ast.AST]


def _is_static_receiver(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Attribute):
        return _is_static_receiver(node.value)
    return False


def _is_direct_attribute_call(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Attribute) and _is_static_receiver(func.value):
        return func.attr
    return None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return '<unknown>'


def _is_safe_media_arg_call(node: ast.Call) -> bool:
    name = _call_name(node).lower()
    return any(pattern in name for pattern in _SAFE_ARG_CALL_PATTERNS)


def _find_unsafe_arg_calls(call_node: ast.Call) -> List[str]:
    unsafe = []
    exprs = list(call_node.args) + [kw.value for kw in call_node.keywords]
    for expr in exprs:
        for sub in ast.walk(expr):
            if isinstance(sub, ast.Call) and not _is_safe_media_arg_call(sub):
                unsafe.append(_call_name(sub))
    return unsafe


class _FunctionAnalyzer(ast.NodeVisitor):
    def __init__(self, func_name: str, module_func_names: Set[str]):
        self.func_name = func_name
        self.module_func_names = module_func_names
        self.callees: Set[str] = set()
        self.direct_media_calls: List[MediaCallInfo] = []
        self.dynamic_flags: List[str] = []
        self._consumed_attrs: Set[int] = set()

    def visit_Expr(self, node: ast.Expr):
        value = node.value
        is_await = False
        call_node = value
        if isinstance(value, ast.Await):
            is_await = True
            call_node = value.value
        if isinstance(call_node, ast.Call):
            method = _is_direct_attribute_call(call_node)
            if method in MEDIA_METHODS:
                unsafe = _find_unsafe_arg_calls(call_node)
                if unsafe:
                    self.dynamic_flags.append(
                        'unsafe_media_argument_side_effect:%s:line%s'
                        % (','.join(unsafe), node.lineno)
                    )
                    self.generic_visit(node)
                    return
                self.direct_media_calls.append(
                    MediaCallInfo(
                        func_name=self.func_name,
                        node=call_node,
                        stmt=node,
                        method=method,
                        is_await=is_await,
                        lineno=node.lineno,
                    )
                )
                return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            if func.id == 'getattr':
                self.dynamic_flags.append('getattr_dispatch:line%s' % node.lineno)
            elif func.id in self.module_func_names:
                self.callees.add(func.id)
            else:
                self.dynamic_flags.append(
                    'unresolved_callable:%s:line%s' % (func.id, node.lineno)
                )
        elif isinstance(func, ast.Attribute):
            self._consumed_attrs.add(id(func))
            if _is_static_receiver(func.value):
                if func.attr in MEDIA_METHODS:
                    self.dynamic_flags.append(
                        'non_atomic_media_use:%s:line%s' % (func.attr, node.lineno)
                    )
            else:
                self.dynamic_flags.append(
                    'dynamic_attribute_receiver:line%s' % node.lineno
                )
        elif isinstance(func, ast.Subscript):
            self.dynamic_flags.append('subscript_dispatch:line%s' % node.lineno)
        elif isinstance(func, ast.Call):
            self.dynamic_flags.append('computed_call_target:line%s' % node.lineno)
        elif isinstance(func, ast.Lambda):
            self.dynamic_flags.append('lambda_dispatch:line%s' % node.lineno)

        self.visit(func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)

    def visit_Attribute(self, node: ast.Attribute):
        if id(node) not in self._consumed_attrs and node.attr in MEDIA_METHODS:
            self.dynamic_flags.append(
                'attribute_alias_reference:%s:line%s' % (node.attr, node.lineno)
            )
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda):
        self.dynamic_flags.append('lambda_present:line%s' % node.lineno)
        self.generic_visit(node)


def scan_reachable_call_graph(tree: ast.AST, entry_points) -> ScanResult:
    module_funcs: Dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_funcs[node.name] = node
    module_func_names = set(module_funcs.keys())

    call_graph: Dict[str, Set[str]] = {}
    direct_media_calls: Dict[str, List[MediaCallInfo]] = {}
    dynamic_flags: Dict[str, List[str]] = {}

    for name, fn in module_funcs.items():
        analyzer = _FunctionAnalyzer(name, module_func_names)
        for stmt in fn.body:
            analyzer.visit(stmt)
        call_graph[name] = analyzer.callees
        direct_media_calls[name] = analyzer.direct_media_calls
        dynamic_flags[name] = analyzer.dynamic_flags

    reverse_callers: Dict[str, Set[str]] = {name: set() for name in module_func_names}
    for caller, callees in call_graph.items():
        for callee in callees:
            if callee in reverse_callers:
                reverse_callers[callee].add(caller)

    reachable: Set[str] = set()
    frontier = [e for e in entry_points if e in module_func_names]
    reachable.update(frontier)
    while frontier:
        nxt = []
        for f in frontier:
            for callee in call_graph.get(f, ()):
                if callee not in reachable:
                    reachable.add(callee)
                    nxt.append(callee)
        frontier = nxt

    return ScanResult(
        call_graph=call_graph,
        reverse_callers=reverse_callers,
        reachable=reachable,
        direct_media_calls=direct_media_calls,
        unresolved_dynamic=dynamic_flags,
        functions=module_funcs,
    )


def _build_text_replacement(node: ast.Expr, call_node: ast.Call, method: str, is_await: bool) -> ast.Expr:
    kind = _MEDIA_KIND[method]
    text_method = _TEXT_METHOD_MAP[method]

    if method.endswith('media_group'):
        count = None
        for arg in call_node.args:
            if isinstance(arg, (ast.List, ast.Tuple)):
                count = len(arg.elts)
                break
        count_text = str(count) if count is not None else 'multiple'
        message_text = '[%s: %s item(s) - media send disabled in admin fast mode]' % (kind, count_text)
    else:
        message_text = '[%s - media send disabled in admin fast mode]' % kind

    new_args = []
    new_keywords = []
    if text_method == 'send_message':
        if call_node.args:
            new_args.append(call_node.args[0])
        for kw in call_node.keywords:
            if kw.arg == 'chat_id':
                new_keywords.append(kw)

    new_args.append(ast.Constant(value=message_text))

    new_call = ast.Call(
        func=ast.Attribute(
            value=copy.deepcopy(call_node.func.value),
            attr=text_method,
            ctx=ast.Load(),
        ),
        args=new_args,
        keywords=new_keywords,
    )
    value = new_call
    if is_await:
        value = ast.Await(value=new_call)
    new_expr = ast.Expr(value=value)
    ast.copy_location(new_expr, node)
    ast.fix_missing_locations(new_expr)
    return new_expr


class _MediaCallTextTransformer(ast.NodeTransformer):
    '''Replaces exactly one atomic direct media-send expression per Expr
    statement with a text-only equivalent, without evaluating original
    media arguments (open/download/thumbnail/binary operations).'''

    def visit_Expr(self, node: ast.Expr):
        value = node.value
        is_await = False
        call_node = value
        if isinstance(value, ast.Await):
            is_await = True
            call_node = value.value
        if isinstance(call_node, ast.Call):
            method = _is_direct_attribute_call(call_node)
            if method in MEDIA_METHODS and not _find_unsafe_arg_calls(call_node):
                return _build_text_replacement(node, call_node, method, is_await)
        return self.generic_visit(node)


def _apply_rewrites(tree: ast.Module, rewrite_targets: Set[str]) -> None:
    transformer = _MediaCallTextTransformer()
    new_body = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in rewrite_targets:
            node = transformer.visit(node)
        new_body.append(node)
    tree.body = new_body
    ast.fix_missing_locations(tree)


def _semantic_hash(node: ast.AST) -> str:
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode('utf-8')).hexdigest()


def _protected_function_hashes(tree: ast.Module, exclude_names: Set[str]) -> Dict[str, str]:
    hashes = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name not in exclude_names:
            hashes[node.name] = _semantic_hash(node)
    return hashes


def transform_cars_ui(source: str, entry_points=None) -> Dict[str, object]:
    entry_points = list(entry_points) if entry_points is not None else list(DEFAULT_ADMIN_ENTRY_ROUTES)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {'status': 'BLOCKED', 'reason': 'syntax_error:%s' % exc, 'candidate': None}

    scan = scan_reachable_call_graph(tree, entry_points)

    missing = [e for e in entry_points if e not in scan.functions]
    if missing:
        return {
            'status': 'BLOCKED',
            'reason': 'missing_entry_points:%s' % sorted(missing),
            'candidate': None,
        }

    rewrite_targets: Set[str] = set()
    block_reasons: List[str] = []

    for func_name in sorted(scan.reachable):
        flags = scan.unresolved_dynamic.get(func_name, [])
        if flags:
            block_reasons.append('%s: %s' % (func_name, flags))
            continue
        media_calls = scan.direct_media_calls.get(func_name, [])
        if not media_calls:
            continue
        if func_name in entry_points:
            rewrite_targets.add(func_name)
            continue
        callers = scan.reverse_callers.get(func_name, set())
        outside_callers = callers - scan.reachable
        if outside_callers:
            block_reasons.append(
                '%s: shared_helper_called_by:%s' % (func_name, sorted(outside_callers))
            )
            continue
        rewrite_targets.add(func_name)

    if block_reasons:
        return {'status': 'BLOCKED', 'reason': '; '.join(block_reasons), 'candidate': None}

    if not rewrite_targets:
        return {
            'status': 'BLOCKED',
            'reason': 'no_direct_media_calls_found_to_rewrite',
            'candidate': None,
        }

    pre_hashes = _protected_function_hashes(tree, rewrite_targets)

    candidate_tree = copy.deepcopy(tree)
    _apply_rewrites(candidate_tree, rewrite_targets)

    post_hashes = _protected_function_hashes(candidate_tree, rewrite_targets)
    if pre_hashes != post_hashes:
        return {
            'status': 'BLOCKED',
            'reason': 'protected_function_hash_mismatch',
            'candidate': None,
        }

    try:
        candidate_src = ast.unparse(candidate_tree)
    except Exception as exc:
        return {'status': 'BLOCKED', 'reason': 'unparse_failed:%s' % exc, 'candidate': None}

    try:
        compile(candidate_src, '<candidate>', 'exec')
    except SyntaxError as exc:
        return {
            'status': 'BLOCKED',
            'reason': 'candidate_compile_failed:%s' % exc,
            'candidate': None,
        }

    post_tree = ast.parse(candidate_src)
    post_scan = scan_reachable_call_graph(post_tree, entry_points)
    for func_name in post_scan.reachable:
        if post_scan.direct_media_calls.get(func_name):
            return {
                'status': 'BLOCKED',
                'reason': 'post_transform_media_still_reachable:%s' % func_name,
                'candidate': None,
            }
        flags = post_scan.unresolved_dynamic.get(func_name)
        if flags:
            return {
                'status': 'BLOCKED',
                'reason': 'post_transform_dynamic_still_reachable:%s:%s' % (func_name, flags),
                'candidate': None,
            }

    return {
        'status': 'OK',
        'reason': 'rewritten',
        'candidate': candidate_src,
        'rewritten_functions': sorted(rewrite_targets),
    }


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/cars_ui_transform.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_031_concurrency.py

```python
"""Offline, deterministic executable tests for TASK 031 phase A:
canonical concurrency primitives and secure writer.

No network access. No PythonAnywhere paths. Only temporary directories,
local processes and local threads are used.
"""
import multiprocessing
import os
import shutil
import stat
import tempfile
import threading
import time
import unittest

from canonical_modules import (
    CrossProcessLock,
    LockEvidence,
    RebuildQueue,
    SafeWriter,
    SingletonGuard,
    _owner_status,
    _pid_alive,
    _process_start_time,
)


def _barrier_worker(lock_path, barrier, result_queue):
    lock = CrossProcessLock(lock_path, stale_after_seconds=5)
    barrier.wait()
    acquired = lock.acquire()
    # Wait until every contender in this round has attempted before the
    # winner releases, proving the winner is held throughout the round.
    barrier.wait()
    if acquired:
        result_queue.put(os.getpid())
        lock.release()
    barrier.wait()


class TestCrossProcessLockSafety(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="task031_")
        self.lock_path = os.path.join(self.tmpdir, "test.lock")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_live_owner_survives_expired_stale_after_seconds(self):
        lock = CrossProcessLock(self.lock_path, stale_after_seconds=0)
        self.assertTrue(lock.acquire())
        time.sleep(0.05)
        other = CrossProcessLock(self.lock_path, stale_after_seconds=0)
        self.assertFalse(other.acquire())
        lock.release()

    def test_dead_owner_stale_takeover(self):
        lock = CrossProcessLock(self.lock_path)
        self.assertTrue(lock.acquire())
        # Fabricate a dead-owner record: a PID that cannot exist.
        fake_pid = 999999
        while True:
            alive = _pid_alive(fake_pid)
            if alive is False:
                break
            fake_pid -= 1
            if fake_pid < 2:
                self.skipTest("could not find an unused pid for this environment")
        evidence = LockEvidence(fake_pid, "999999999", "deadtoken", time.time())
        with open(self.lock_path, "w") as fh:
            fh.write(evidence.to_line())
        lock._owned = False
        newcomer = CrossProcessLock(self.lock_path)
        self.assertTrue(newcomer.acquire())
        newcomer.release()

    def test_pid_reuse_start_mismatch_takeover(self):
        # pid is alive (this test process) but start_time is wrong ->
        # must be classified 'dead' (mismatch), allowing safe takeover.
        evidence = LockEvidence(os.getpid(), "not-the-real-start-time", "tok", time.time())
        with open(self.lock_path, "w") as fh:
            fh.write(evidence.to_line())
        status = _owner_status(evidence)
        self.assertEqual(status, "dead")
        newcomer = CrossProcessLock(self.lock_path)
        self.assertTrue(newcomer.acquire())
        newcomer.release()

    def test_unknown_identity_fails_closed(self):
        import canonical_modules as canon

        real_pid = os.getpid()
        evidence = LockEvidence(real_pid, _process_start_time(real_pid) or "x", "tok", time.time())
        with open(self.lock_path, "w") as fh:
            fh.write(evidence.to_line())

        original = canon._process_start_time
        canon._process_start_time = lambda pid: None
        try:
            status = _owner_status(evidence)
            self.assertEqual(status, "unknown")
            newcomer = CrossProcessLock(self.lock_path)
            self.assertFalse(newcomer.acquire())
        finally:
            canon._process_start_time = original

    def test_foreign_token_cannot_release(self):
        lock = CrossProcessLock(self.lock_path)
        self.assertTrue(lock.acquire())
        impostor = CrossProcessLock(self.lock_path)
        impostor._owned = True  # simulate an impostor believing it owns it
        impostor.release()
        # Real owner's evidence must remain untouched.
        self.assertTrue(os.path.exists(self.lock_path))
        current = lock._read_evidence()
        self.assertIsNotNone(current)
        self.assertEqual(current.token, lock.token)
        lock.release()

    def test_release_lifecycle_never_raises(self):
        lock = CrossProcessLock(self.lock_path)
        self.assertTrue(lock.acquire())
        lock.release()
        lock.release()  # double release must not raise

        lock2 = CrossProcessLock(self.lock_path)
        self.assertTrue(lock2.acquire())
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            pass
        finally:
            lock2.release()
        lock2.release()

        lock3 = CrossProcessLock(self.lock_path)
        self.assertTrue(lock3.acquire())
        lock3.release()  # simulates an idempotent atexit invocation

        lock4 = CrossProcessLock(self.lock_path)
        self.assertTrue(lock4.acquire())
        shutil.rmtree(self.tmpdir)
        # Deleted parent: release must be a safe no-op, never recreate it.
        lock4.release()
        self.assertFalse(os.path.exists(self.tmpdir))


class TestMultiprocessBarrier(unittest.TestCase):
    def test_100_rounds_exactly_one_winner(self):
        tmpdir = tempfile.mkdtemp(prefix="task031_mp_")
        try:
            lock_path = os.path.join(tmpdir, "barrier.lock")
            contenders = 4
            rounds = 100
            ctx = multiprocessing.get_context("fork")
            for i in range(rounds):
                barrier = ctx.Barrier(contenders)
                result_queue = ctx.Queue()
                procs = [
                    ctx.Process(target=_barrier_worker, args=(lock_path, barrier, result_queue))
                    for _ in range(contenders)
                ]
                for p in procs:
                    p.start()
                for p in procs:
                    p.join(timeout=15)
                    self.assertFalse(p.is_alive(), f"round {i}: worker did not finish")
                winners = []
                while not result_queue.empty():
                    winners.append(result_queue.get())
                self.assertEqual(len(winners), 1, f"round {i} winners={winners}")
                for p in (lock_path, lock_path + ".guard"):
                    if os.path.exists(p):
                        try:
                            os.unlink(p)
                        except FileNotFoundError:
                            pass
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestRebuildQueue(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="task031_rq_")
        self.lock_path = os.path.join(self.tmpdir, "rebuild.lock")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_enqueue_returns_promptly_while_callback_is_slow(self):
        started = threading.Event()
        release_cb = threading.Event()

        def slow_cb():
            started.set()
            release_cb.wait(timeout=3)

        q = RebuildQueue(slow_cb, self.lock_path)
        t0 = time.time()
        result = q.enqueue()
        elapsed = time.time() - t0
        self.assertEqual(result, "accepted")
        self.assertLess(elapsed, 0.5)
        self.assertTrue(started.wait(timeout=2))
        release_cb.set()
        q.shutdown(timeout=5)
        self.assertEqual(q.runs, 1)

    def test_burst_produces_one_active_run_and_one_followup(self):
        calls = []
        gate = threading.Event()

        def cb():
            gate.wait(timeout=3)
            calls.append(1)

        q = RebuildQueue(cb, self.lock_path)
        r1 = q.enqueue()
        self.assertEqual(r1, "accepted")
        for _ in range(10):
            q.enqueue()
        gate.set()
        q.shutdown(timeout=5)
        self.assertEqual(len(calls), 2)
        self.assertEqual(q.runs, 2)
        self.assertGreaterEqual(q.coalesced, 1)

    def test_callback_exception_is_bounded_no_spin(self):
        attempts = {"n": 0}

        def failing_cb():
            attempts["n"] += 1
            raise ValueError("deliberate failure")

        q = RebuildQueue(failing_cb, self.lock_path)
        q.enqueue()
        deadline = time.time() + 3
        while attempts["n"] == 0 and time.time() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)
        q.shutdown(timeout=5)
        self.assertEqual(attempts["n"], 1)
        self.assertEqual(len(q.errors), 1)
        self.assertEqual(q.runs, 0)


class TestSafeWriter(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp(prefix="task031_sw_")

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_reject_absolute_path(self):
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("/etc/passwd", b"x")

    def test_reject_traversal(self):
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("../escape.txt", b"x")

    def test_reject_symlink_parent(self):
        real_sub = os.path.join(self.run_dir, "realdir")
        os.mkdir(real_sub)
        link_sub = os.path.join(self.run_dir, "linkdir")
        os.symlink(real_sub, link_sub)
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("linkdir/file.txt", b"x")

    def test_reject_target_symlink(self):
        target = os.path.join(self.run_dir, "file.txt")
        os.symlink("/etc/passwd", target)
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("file.txt", b"x")

    def test_reject_hardlink_target(self):
        other = os.path.join(self.run_dir, "other.txt")
        with open(other, "w") as fh:
            fh.write("hello")
        target = os.path.join(self.run_dir, "file.txt")
        os.link(other, target)
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("file.txt", b"x")

    def test_reject_non_regular_target(self):
        target = os.path.join(self.run_dir, "fifo")
        os.mkfifo(target)
        w = SafeWriter(self.run_dir)
        with self.assertRaises(ValueError):
            w.write_bytes("fifo", b"x")

    def test_reject_deleted_parent(self):
        w = SafeWriter(self.run_dir)
        shutil.rmtree(self.run_dir)
        with self.assertRaises(Exception):
            w.write_bytes("sub/file.txt", b"x")

    def test_replacement_race_is_rejected(self):
        w = SafeWriter(self.run_dir)

        def hook(target, target_dir):
            if os.path.lexists(target):
                os.unlink(target)
            os.symlink("/etc/passwd", target)

        w._pre_replace_hook = hook
        with self.assertRaises(ValueError):
            w.write_bytes("race.txt", b"payload")
        target = os.path.join(self.run_dir, "race.txt")
        self.assertTrue(os.path.islink(target))

    def test_successful_write_atomic_hash_recorded(self):
        w = SafeWriter(self.run_dir)
        data = b"hello world, byte exact\x00\x01\x02"
        target = w.write_bytes("reports/out.bin", data)
        with open(target, "rb") as fh:
            on_disk = fh.read()
        self.assertEqual(on_disk, data)
        st = os.stat(target)
        self.assertEqual(st.st_nlink, 1)
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        self.assertEqual(len(w.ledger), 1)
        entry = w.ledger[0]
        self.assertEqual(entry["relative_path"], os.path.normpath("reports/out.bin"))
        self.assertEqual(entry["size"], len(data))
        import hashlib
        self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())


class TestCompatibilityImports(unittest.TestCase):
    def test_reexports_resolve_to_canonical_objects(self):
        import canonical_modules as canon
        import cross_process_lock as cpl
        import rebuild_queue as rq
        import safe_writer as sw
        import singleton_guard as sg

        self.assertIs(cpl.CrossProcessLock, canon.CrossProcessLock)
        self.assertIs(cpl.LockEvidence, canon.LockEvidence)
        self.assertIs(cpl.SingletonGuard, canon.SingletonGuard)
        self.assertIs(rq.RebuildQueue, canon.RebuildQueue)
        self.assertIs(sw.SafeWriter, canon.SafeWriter)
        self.assertIs(sg.CrossProcessLock, canon.CrossProcessLock)
        self.assertIs(sg.SingletonGuard, canon.SingletonGuard)


if __name__ == "__main__":
    unittest.main()


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_031_concurrency.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_032_orchestration.py

```python
"""Offline, deterministic tests for TASK 032: real orchestration entry
point, secure run lifecycle, measured phases, and manifest/verification
integrity. No network access. No /home/Carix paths. Only temporary
directories, local files, and fake HTTPS openers are used.
"""
import os
import sys
import json
import time
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import crm_speed_gate_a as gate_a
import build_manifest
import verify_gate_a
import RUN_GATE_A_CRM_SPEED as launcher

from test_crm_speed_gate_a import (
    CLEAN_CARS_UI, CLEAN_USERCUSTOMIZE, CLEAN_AVTOPEREDACHA,
    DB_FUNCTION_SOURCE, _FakeOpener,
)

CARS_UI_SIDE_EFFECT_SOURCE = """def gallery(update, context):
    undefined_name_reference_only_fails_if_executed()
def video_gallery(update, context): pass
def diag_photo_show(update, context): pass
def diag_video_show(update, context): pass
"""


def _fake_opener_404():
    return _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))


def _make_temp_config():
    tmp = tempfile.mkdtemp(prefix="task032_")
    names = [
        "usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
        "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py",
    ]
    required = []
    for name in names:
        p = os.path.join(tmp, name)
        if name == "cars_ui.py":
            content = CLEAN_CARS_UI
        elif name == "usercustomize.py":
            content = CLEAN_USERCUSTOMIZE
        elif name == "avtoperedacha.py":
            content = CLEAN_AVTOPEREDACHA
        else:
            content = "# fixture" + os.linesep
        with open(p, "w") as fh:
            fh.write(content)
        required.append(p)

    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    required.append(db_path)

    backup_path = os.path.join(tmp, "backup.tar.gz")
    with open(backup_path, "wb") as fh:
        fh.write(b"fixture-backup-bytes")
    backup_sha = gate_a._sha256_file(backup_path)

    site_root1 = os.path.join(tmp, "site")
    site_root2 = os.path.join(tmp, "video")
    site_root3 = os.path.join(tmp, "public_html")
    for root in (site_root1, site_root2, site_root3):
        os.makedirs(root)
        with open(os.path.join(root, "index.html"), "w") as fh:
            fh.write("<html></html>")
        with open(os.path.join(root, "katalog.html"), "w") as fh:
            fh.write("<html></html>")

    run_root = os.path.join(tmp, "qa_root")
    os.makedirs(run_root, mode=0o700)

    config = {
        "required_inputs": required,
        "site_roots": {
            site_root1: ["index.html", "katalog.html"],
            site_root2: ["index.html", "katalog.html"],
            site_root3: ["index.html", "katalog.html"],
        },
        "ua0009_url": "https://example.com/UA-0009.html",
        "run_root": run_root,
        "backup_archive": backup_path,
        "backup_archive_sha256": backup_sha,
        "protected_function_names": [],
        "db_function_source": DB_FUNCTION_SOURCE,
        "min_free_bytes": 1024,
    }
    return config, tmp


class _TempConfigCase(unittest.TestCase):
    def setUp(self):
        self.cfg, self.tmp = _make_temp_config()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class LauncherTests(unittest.TestCase):
    def test_launcher_calls_orchestration_and_propagates_pass(self):
        fake_receipt = {
            "status": "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL",
            "run_id": "x", "unmet_predicates": [], "phases": [], "production_write": "NO",
        }
        calls = []

        def fake_orchestrate(cfg):
            calls.append(cfg)
            return fake_receipt

        rc = launcher.main(orchestrate=fake_orchestrate, config={"marker": True})
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [{"marker": True}])

    def test_launcher_propagates_blocked_nonzero(self):
        fake_receipt = {
            "status": "BLOCKED", "run_id": "x", "unmet_predicates": ["a"],
            "phases": [], "production_write": "NO",
        }
        rc = launcher.main(orchestrate=lambda cfg: fake_receipt, config={})
        self.assertEqual(rc, 1)

    def test_launcher_internal_error_is_nonzero(self):
        def boom(cfg):
            raise RuntimeError("deliberate")
        rc = launcher.main(orchestrate=boom, config={})
        self.assertEqual(rc, 1)


class RunDirCreationTests(_TempConfigCase):
    def test_exactly_one_validated_run_dir_created_before_safewriter(self):
        seen = []
        original_init = gate_a.SafeWriter.__init__

        def spy_init(self, run_dir):
            seen.append(os.path.isdir(run_dir) and not os.path.islink(run_dir))
            return original_init(self, run_dir)

        with mock.patch.object(gate_a.SafeWriter, "__init__", spy_init):
            gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())

        self.assertTrue(seen)
        self.assertTrue(all(seen))
        subdirs = [
            d for d in os.listdir(self.cfg["run_root"])
            if os.path.isdir(os.path.join(self.cfg["run_root"], d))
        ]
        self.assertEqual(len(subdirs), 1)


class SecureInputTests(_TempConfigCase):
    def test_symlink_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        os.remove(target)
        os.symlink(os.path.join(self.tmp, "crm.db"), target)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("symlink_input" in b for b in receipt.get("blockers", [])))

    def test_missing_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        os.remove(target)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("missing_input" in b for b in receipt.get("blockers", [])))

    def test_hardlink_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        other = os.path.join(self.tmp, "other_copy.py")
        os.link(target, other)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("hard_linked_input" in b for b in receipt.get("blockers", [])))


class BackupOrderingTests(_TempConfigCase):
    def test_backup_mismatch_blocks_before_candidate_creation(self):
        self.cfg["backup_archive_sha256"] = "0" * 64
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertNotIn("candidates_compile", receipt["evidence"])
        self.assertTrue(any("backup_verification_failed" in b for b in receipt.get("blockers", [])))


class LockDuplicateTests(_TempConfigCase):
    def test_duplicate_lock_returns_promptly_without_altering_owner_evidence(self):
        qa_root_real = os.path.realpath(self.cfg["run_root"])
        holder = canonical_modules.CrossProcessLock(os.path.join(qa_root_real, "gate_a.lock"))
        self.assertTrue(holder.acquire())
        try:
            before = holder._read_evidence()
            t0 = time.time()
            receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
            elapsed = time.time() - t0
            after = holder._read_evidence()
            self.assertLess(elapsed, 2.0)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertIn("gate_a_lock_held", receipt.get("blockers", []))
            self.assertEqual(before.token, after.token)
        finally:
            holder.release()


class PhaseOrderTests(_TempConfigCase):
    def test_phase_order_and_measured_durations(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        phase_nums = [p["phase"] for p in receipt["phases"]]
        self.assertEqual(phase_nums, [20, 40, 60, 80, 100])
        for p in receipt["phases"]:
            self.assertGreaterEqual(p["end"], p["start"])
            self.assertGreaterEqual(p["duration"], 0)
        self.assertEqual(receipt["phases"][-1]["status"], "finished")


class InventorySurroundTests(_TempConfigCase):
    def test_inventories_surround_entire_workload(self):
        call_count = {"n": 0}
        original = gate_a.scan_bounded_inventory

        def counting(*args, **kwargs):
            call_count["n"] += 1
            return original(*args, **kwargs)

        with mock.patch.object(gate_a, "scan_bounded_inventory", counting):
            receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())

        n_roots = len(self.cfg["site_roots"])
        self.assertEqual(call_count["n"], n_roots * 2)
        self.assertIn("before", receipt["site_inventories"])
        self.assertIn("after", receipt["site_inventories"])


class CompileOnlyTests(_TempConfigCase):
    def test_candidates_compile_without_import_execution(self):
        cars_ui_path = [p for p in self.cfg["required_inputs"] if p.endswith("cars_ui.py")][0]
        with open(cars_ui_path, "w") as fh:
            fh.write(CARS_UI_SIDE_EFFECT_SOURCE)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertIn("candidates_compile", receipt["evidence"])
        self.assertEqual(receipt["evidence"]["candidates_compile"]["status"], "OK")


def _clean_pass_fixture(tmp):
    required = []
    names = [
        "usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
        "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py",
    ]
    for name in names:
        p = os.path.join(tmp, name)
        with open(p, "w") as fh:
            fh.write("# fixture" + os.linesep)
        required.append(p)
    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    required.append(db_path)

    backup_archive = os.path.join(tmp, "backup.tar.gz")
    with open(backup_archive, "wb") as fh:
        fh.write(b"fixture-backup-bytes")
    backup_sha256 = gate_a._sha256_file(backup_archive)

    site_root = os.path.join(tmp, "site")
    os.makedirs(site_root)
    with open(os.path.join(site_root, "index.html"), "w") as fh:
        fh.write("<html></html>")
    with open(os.path.join(site_root, "katalog.html"), "w") as fh:
        fh.write("<html></html>")

    run_dir = os.path.join(tmp, "run")
    fp = {"a": 1}
    return {
        "required_inputs": required,
        "backup_archive": backup_archive,
        "backup_archive_sha256": backup_sha256,
        "cars_ui_source": CLEAN_CARS_UI,
        "usercustomize_source": CLEAN_USERCUSTOMIZE,
        "avtoperedacha_source": CLEAN_AVTOPEREDACHA,
        "protected_fingerprints_before": fp,
        "protected_fingerprints_after": dict(fp),
        "db_path": db_path,
        "ua0009_fingerprint_before": {"h": "same"},
        "ua0009_fingerprint_after": {"h": "same"},
        "ua0009_url": "https://example.com/UA-0009.html",
        "ua0009_opener": _fake_opener_404(),
        "site_root": site_root,
        "allowed_site_names": ["index.html", "katalog.html"],
        "protected_function_names": ["upload_media", "delete_media"],
        "tmp_dir": tmp,
        "db_function_source": DB_FUNCTION_SOURCE,
        "site_before": {"x": 1},
        "site_after": {"x": 1},
        "run_dir": run_dir,
    }


class ManifestVerifyTests(_TempConfigCase):
    def test_receipt_and_manifest_hash_tamper_detected(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertIsNotNone(receipt.get("run_id"))
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        self.assertTrue(os.path.isdir(run_dir))

        package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
        manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh)

        receipt_path = os.path.join(run_dir, "receipt.json")
        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path)
        self.assertTrue(ok, reason)

        with open(receipt_path, "r") as fh:
            data = fh.read()
        with open(receipt_path, "w") as fh:
            fh.write(data + os.linesep + "tampered")

        ok2, reason2 = verify_gate_a.verify_receipt(receipt_path, manifest_path)
        self.assertFalse(ok2)

    def test_missing_required_predicate_blocks_verification(self):
        tmp2 = tempfile.mkdtemp(prefix="task032_legacy_")
        try:
            fixture = _clean_pass_fixture(tmp2)
            receipt = gate_a.run_gate_a(fixture)
            self.assertEqual(receipt["status"], "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL")
            del receipt["evidence"]["backup_verified"]
            receipt_path = os.path.join(tmp2, "tampered_receipt.json")
            with open(receipt_path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(receipt_path)
            self.assertFalse(ok)
            self.assertTrue(reason.startswith("missing_or_malformed_predicate"))
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_altered_candidate_diff_report_blocks_verification(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
        manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh)
        report_path = os.path.join(run_dir, "report.md")
        with open(report_path, "a") as fh:
            fh.write("tampered-line" + os.linesep)
        ok, reason = verify_gate_a.verify_receipt(os.path.join(run_dir, "receipt.json"), manifest_path)
        self.assertFalse(ok)
        self.assertEqual(reason, "report_hash_mismatch")


class BlockedNonzeroTests(_TempConfigCase):
    def test_blocked_orchestration_returns_nonzero_with_complete_evidence(self):
        self.cfg["backup_archive_sha256"] = "0" * 64

        def orchestrate(cfg):
            return gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())

        rc = launcher.main(orchestrate=orchestrate, config=self.cfg)
        self.assertEqual(rc, 1)

    def test_blocked_receipt_has_bounded_evidence(self):
        self.cfg["backup_archive_sha256"] = "0" * 64
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("phases", receipt)
        self.assertIn("blockers", receipt)
        self.assertEqual(receipt["production_write"], "NO")


class RebuildQueueAckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task032_rq_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_slow_callback_still_yields_prompt_enqueue_return(self):
        lock_path = os.path.join(self.tmp, "rebuild.lock")
        release_cb = threading.Event()

        def slow_cb():
            release_cb.wait(timeout=3)

        q = canonical_modules.RebuildQueue(slow_cb, lock_path)
        t0 = time.time()
        status = q.enqueue()
        elapsed = time.time() - t0
        self.assertEqual(status, "accepted")
        self.assertLess(elapsed, 0.20)
        release_cb.set()
        q.shutdown(timeout=5)

    def test_immediate_observation_sees_callback_entry(self):
        lock_path = os.path.join(self.tmp, "rebuild.lock")
        entered = threading.Event()

        def cb():
            entered.set()

        q = canonical_modules.RebuildQueue(cb, lock_path)
        status = q.enqueue()
        self.assertEqual(status, "accepted")
        self.assertTrue(entered.is_set())
        q.shutdown(timeout=5)


if __name__ == "__main__":
    unittest.main()


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_032_orchestration.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_035_integration.py

```python
"""Offline, deterministic tests for TASK 035: evidence integration and
complete compatibility between the TASK 032 orchestrator and the
TASK 034 evidence modules. No network access. No /home/Carix or
production paths. No PythonAnywhere access. No Gate A execution against
production. Only temporary directories, local files, and fake HTTPS
openers are used.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crm_speed_gate_a as gate_a
import build_manifest
import verify_gate_a
import sqlite_ownership
import ua0009_publication_check

import test_task_032_orchestration as t032
from test_task_032_orchestration import _make_temp_config, _fake_opener_404, CARS_UI_SIDE_EFFECT_SOURCE

PII_SEED = "no-pii-seed-marker-should-not-leak-task035"


# ---------------------------------------------------------------------------
# Regression 1: candidates_compile present after cars_ui semantic block
# ---------------------------------------------------------------------------

class Regression1CandidatesCompileAfterBlockTests(unittest.TestCase):
    def test_candidates_compile_present_from_original_bytes_and_final_status_blocked(self):
        cfg, tmp = _make_temp_config()
        try:
            cars_ui_path = [p for p in cfg["required_inputs"] if p.endswith("cars_ui.py")][0]
            with open(cars_ui_path, "w") as fh:
                fh.write(CARS_UI_SIDE_EFFECT_SOURCE)
            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            self.assertIn("candidates_compile", receipt["evidence"])
            compile_ev = receipt["evidence"]["candidates_compile"]
            self.assertEqual(compile_ev["status"], "OK")
            self.assertEqual(compile_ev.get("candidate_origin"), "original_due_to_transform_block")
            # Safe compile evidence never by itself permits a final PASS.
            self.assertEqual(receipt["status"], "BLOCKED")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Regression 2: build_manifest historical vs canonical call forms
# ---------------------------------------------------------------------------

class Regression2ManifestCompatTests(unittest.TestCase):
    def test_historical_manifest_call_with_receipt_dict_is_deterministic(self):
        cfg, tmp = _make_temp_config()
        try:
            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            run_dir = os.path.join(cfg["run_root"], receipt["run_id"])
            package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
            manifest1 = build_manifest.build_manifest(package_dir, run_dir, receipt)
            manifest2 = build_manifest.build_manifest(package_dir, run_dir, receipt)
            self.assertIn("receipt_sha256", manifest1)
            self.assertIn("report_sha256", manifest1)
            self.assertEqual(build_manifest.canonical_json(manifest1), build_manifest.canonical_json(manifest2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_canonical_manifest_call_still_works_with_bounded_list(self):
        tmp = tempfile.mkdtemp(prefix="task035_manifest_")
        try:
            package_dir = os.path.join(tmp, "pkg")
            os.makedirs(package_dir)
            with open(os.path.join(package_dir, "a.py"), "w") as fh:
                fh.write("x = 1\n")
            run_dir = os.path.join(tmp, "run")
            os.makedirs(run_dir)
            f1 = os.path.join(run_dir, "f1.txt")
            f2 = os.path.join(run_dir, "f2.txt")
            with open(f1, "w") as fh:
                fh.write("a")
            with open(f2, "w") as fh:
                fh.write("b")
            m1 = build_manifest.build_manifest(package_dir, run_dir, run_artifact_paths={"multi": [f1, f2]})
            m2 = build_manifest.build_manifest(package_dir, run_dir, run_artifact_paths={"multi": [f1, f2]})
            self.assertIsInstance(m1["run_artifact_hashes"]["multi"], list)
            self.assertEqual(len(m1["run_artifact_hashes"]["multi"]), 2)
            self.assertEqual(build_manifest.canonical_json(m1), build_manifest.canonical_json(m2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dict_artifact_value_blocks_cleanly(self):
        tmp = tempfile.mkdtemp(prefix="task035_manifest_dict_")
        try:
            package_dir = os.path.join(tmp, "pkg")
            os.makedirs(package_dir)
            with open(os.path.join(package_dir, "a.py"), "w") as fh:
                fh.write("x = 1\n")
            run_dir = os.path.join(tmp, "run")
            os.makedirs(run_dir)
            f1 = os.path.join(run_dir, "f1.txt")
            with open(f1, "w") as fh:
                fh.write("a")
            with self.assertRaises(ValueError):
                build_manifest.build_manifest(package_dir, run_dir, run_artifact_paths={"bad": {"nested": f1}})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Regression 3: dual-schema fail-closed verifier
# ---------------------------------------------------------------------------

class Regression3VerifierSchemaTests(unittest.TestCase):
    def _historical_predicates_ok(self):
        return {k: {"status": "OK"} for k in verify_gate_a.HISTORICAL_REQUIRED_PREDICATES}

    def _focused_predicates_ok(self):
        return {k: {"status": "OK"} for k in verify_gate_a.REQUIRED_PREDICATES}

    def test_historical_schema_pass_valid_fixture(self):
        tmp = tempfile.mkdtemp(prefix="task035_hist_")
        try:
            receipt = {
                "status": "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL",
                "production_write": "NO",
                "evidence": self._historical_predicates_ok(),
                "unmet_predicates": [],
            }
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertTrue(ok, reason)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_focused_schema_pass_valid_fixture(self):
        tmp = tempfile.mkdtemp(prefix="task035_foc_")
        try:
            receipt = {
                "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
                "predicates": self._focused_predicates_ok(), "unmet_predicates": [],
            }
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertTrue(ok, reason)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mixed_schema_blocks_cleanly(self):
        tmp = tempfile.mkdtemp(prefix="task035_mix_")
        try:
            receipt = {
                "status": "BLOCKED", "production_write": "NO",
                "evidence": self._historical_predicates_ok(),
                "predicates": self._focused_predicates_ok(),
            }
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertFalse(ok)
            self.assertEqual(reason, "mixed_schema_forms")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_historical_predicate_exact_prefix(self):
        tmp = tempfile.mkdtemp(prefix="task035_missp_")
        try:
            preds = self._historical_predicates_ok()
            del preds["backup_verified"]
            receipt = {"status": "BLOCKED", "production_write": "NO", "evidence": preds}
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertFalse(ok)
            self.assertEqual(reason, "missing_or_malformed_predicate:backup_verified")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_malformed_focused_predicate_blocks(self):
        tmp = tempfile.mkdtemp(prefix="task035_foc_bad_")
        try:
            preds = self._focused_predicates_ok()
            preds["pii_not_emitted"] = "not-a-dict"
            receipt = {
                "status": "BLOCKED", "production_write": "NO", "pii_emitted": "NO",
                "predicates": preds,
            }
            path = os.path.join(tmp, "receipt.json")
            with open(path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(path, run_dir=tmp)
            self.assertFalse(ok)
            self.assertEqual(reason, "missing_or_malformed_predicate:pii_not_emitted")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Regression 4: two-argument verify_receipt auto-binds run_dir/report.md
# ---------------------------------------------------------------------------

class Regression4ReportAutoBindTests(unittest.TestCase):
    def test_report_tamper_detected_with_two_positional_args(self):
        cfg, tmp = _make_temp_config()
        try:
            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            run_dir = os.path.join(cfg["run_root"], receipt["run_id"])
            package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
            manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
            manifest_path = os.path.join(run_dir, "manifest.json")
            with open(manifest_path, "w") as fh:
                json.dump(manifest, fh)
            report_path = os.path.join(run_dir, "report.md")
            with open(report_path, "a") as fh:
                fh.write("tampered-line" + os.linesep)
            ok, reason = verify_gate_a.verify_receipt(os.path.join(run_dir, "receipt.json"), manifest_path)
            self.assertFalse(ok)
            self.assertEqual(reason, "report_hash_mismatch")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_receipt_tamper_blocks(self):
        cfg, tmp = _make_temp_config()
        try:
            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            run_dir = os.path.join(cfg["run_root"], receipt["run_id"])
            package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
            manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
            manifest_path = os.path.join(run_dir, "manifest.json")
            with open(manifest_path, "w") as fh:
                json.dump(manifest, fh)
            receipt_path = os.path.join(run_dir, "receipt.json")
            with open(receipt_path, "a") as fh:
                fh.write(" ")
            ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path)
            self.assertFalse(ok)
            self.assertEqual(reason, "receipt_hash_mismatch")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Canonical delegation identity / monkeypatch tests
# ---------------------------------------------------------------------------

class DelegationIdentityTests(unittest.TestCase):
    def test_publication_probe_delegates_to_canonical_function(self):
        cfg, tmp = _make_temp_config()
        try:
            calls = []
            original = ua0009_publication_check.canonical_probe_ua0009

            def spy(url, opener=None, timeout=5.0):
                calls.append(url)
                return original(url, opener=opener, timeout=timeout)

            with mock.patch.object(gate_a.ua0009_publication_check, "canonical_probe_ua0009", spy):
                gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            self.assertTrue(calls)
            self.assertEqual(calls[0], cfg["ua0009_url"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sqlite_ownership_evidence_delegates_to_canonical_function(self):
        cfg, tmp = _make_temp_config()
        try:
            cfg["ua0009_table"] = "t"
            cfg["ua0009_id_column"] = "id"
            cfg["ua0009_id_value"] = "1"
            db_path = [p for p in cfg["required_inputs"] if p.endswith("crm.db")][0]
            conn = sqlite3.connect(db_path)
            # The temporary fixture already creates table t with column id
            # INTEGER (see _make_temp_config). Reuse that existing column
            # instead of duplicating it, and insert one deterministic row
            # whose id is compatible with cfg["ua0009_id_value"] == "1".
            conn.execute("INSERT INTO t (id) VALUES (1)")
            conn.commit()
            conn.close()

            calls = []
            original = sqlite_ownership.collect_ua0009_ownership_evidence

            def spy(*a, **kw):
                calls.append(a)
                return original(*a, **kw)

            with mock.patch.object(gate_a.sqlite_ownership, "collect_ua0009_ownership_evidence", spy):
                gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            self.assertEqual(len(calls), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# SQLite before/after ordering (not adjacent, surrounding the workload)
# ---------------------------------------------------------------------------

class SqliteBeforeAfterOrderingTests(unittest.TestCase):
    def test_sqlite_calls_surround_the_full_workload(self):
        cfg, tmp = _make_temp_config()
        try:
            cfg["ua0009_table"] = "t"
            cfg["ua0009_id_column"] = "rowid"
            cfg["ua0009_id_value"] = "1"
            events = []
            original_sqlite = sqlite_ownership.collect_ua0009_ownership_evidence
            original_transform = gate_a.transform_cars_ui

            def spy_sqlite(*a, **kw):
                events.append("sqlite")
                return original_sqlite(*a, **kw)

            def spy_transform(*a, **kw):
                events.append("transform")
                return original_transform(*a, **kw)

            with mock.patch.object(gate_a.sqlite_ownership, "collect_ua0009_ownership_evidence", spy_sqlite), \
                 mock.patch.object(gate_a, "transform_cars_ui", spy_transform):
                gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())

            self.assertGreaterEqual(len(events), 3)
            self.assertEqual(events[0], "sqlite")
            self.assertEqual(events[-1], "sqlite")
            self.assertIn("transform", events)
            self.assertGreater(events.index("transform"), events.index("sqlite"))
            self.assertLess(events.index("transform"), len(events) - 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# PII safety
# ---------------------------------------------------------------------------

class PIISafetyTests(unittest.TestCase):
    def test_pii_seed_never_appears_in_receipt_manifest_or_report(self):
        cfg, tmp = _make_temp_config()
        try:
            db_path = [p for p in cfg["required_inputs"] if p.endswith("crm.db")][0]
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE ua0009 (id TEXT, secret TEXT)")
            conn.execute("INSERT INTO ua0009 (id, secret) VALUES ('UA-0009', ?)", (PII_SEED,))
            conn.commit()
            conn.close()
            cfg["ua0009_table"] = "ua0009"
            cfg["ua0009_id_column"] = "id"
            cfg["ua0009_id_value"] = "UA-0009"

            receipt = gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())
            serialized = json.dumps(receipt, default=str)
            self.assertNotIn(PII_SEED, serialized)

            run_dir = os.path.join(cfg["run_root"], receipt["run_id"])
            package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
            manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
            self.assertNotIn(PII_SEED, build_manifest.canonical_json(manifest))

            with open(os.path.join(run_dir, "report.md")) as fh:
                report_text = fh.read()
            self.assertNotIn(PII_SEED, report_text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Compile-only sanity for the modules touched by this task
# ---------------------------------------------------------------------------

class CompileSanityTests(unittest.TestCase):
    def test_modules_compile(self):
        import py_compile
        base = os.path.dirname(os.path.abspath(__file__))
        for name in ("crm_speed_gate_a.py", "build_manifest.py", "verify_gate_a.py", "test_task_035_integration.py"):
            py_compile.compile(os.path.join(base, name), doraise=True)


if __name__ == "__main__":
    unittest.main()


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_035_integration.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_crm_speed_gate_a.py

```python
"""Offline test suite for CRM-SPEED-001 Gate A package (round 3 corrections).

Run with: python -m unittest test_crm_speed_gate_a -v
from inside cloud/crm_speed_optimization/. This suite never touches
production, /home/Carix, or PythonAnywhere.
"""
import os
import sys
import time
import uuid
import random
import sqlite3
import tempfile
import unittest
import multiprocessing
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import cross_process_lock
import rebuild_queue as rebuild_queue_module
import safe_writer as safe_writer_module
import crm_speed_gate_a as gate_a

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
from crm_speed_gate_a import (
    scan_reachable_call_graph, transform_cars_ui, measure_deterministic_repeat,
    scan_bounded_inventory, check_ua0009_not_public, evaluate_gate_a, run_gate_a,
    DEFAULT_MAX_FILES_PER_ROOT, ADMIN_ROUTE_NAMES,
)


# ---------------------------------------------------------------------------
# Identity assertions (correction D)
# ---------------------------------------------------------------------------

class IdentityTests(unittest.TestCase):
    def test_cross_process_lock_identity(self):
        self.assertIs(cross_process_lock.CrossProcessLock, canonical_modules.CrossProcessLock)
        self.assertIs(gate_a.CrossProcessLock, canonical_modules.CrossProcessLock)

    def test_rebuild_queue_identity(self):
        self.assertIs(rebuild_queue_module.RebuildQueue, canonical_modules.RebuildQueue)
        self.assertIs(gate_a.RebuildQueue, canonical_modules.RebuildQueue)

    def test_safe_writer_identity(self):
        self.assertIs(safe_writer_module.SafeWriter, canonical_modules.SafeWriter)
        self.assertIs(gate_a.SafeWriter, canonical_modules.SafeWriter)

    def test_singleton_guard_identity(self):
        self.assertIs(cross_process_lock.SingletonGuard, canonical_modules.SingletonGuard)
        self.assertIs(gate_a.SingletonGuard, canonical_modules.SingletonGuard)


# ---------------------------------------------------------------------------
# Correction A: dynamic dispatch call-graph scanner + cars_ui transform
# ---------------------------------------------------------------------------

class CarsUiTransformTests(unittest.TestCase):
    def test_dynamic_dispatch_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn(open('x.jpg', 'rb'))\n"
            "def video_gallery(update, context):\n"
            "    pass\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any(r.startswith("dynamic_dispatch_forbidden") for r in result["reasons"]))

    def test_getattr_computed_name_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    name = pick_name()\n"
            "    fn = getattr(update.message, name)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_bound_method_alias_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    sender(open('x.jpg','rb'))\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_dict_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = {'photo': update.message.reply_photo}\n"
            "    handlers['photo']()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_list_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = [update.message.reply_photo]\n"
            "    handlers[0]()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_lambda_media_call_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    f = lambda: update.message.reply_photo(open('x.jpg','rb'))\n"
            "    f()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_return_alias_blocks(self):
        source = (
            "def _pick(update):\n"
            "    return update.message.reply_photo\n"
            "def gallery(update, context):\n"
            "    fn = _pick(update)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_await_alias_blocks(self):
        source = (
            "async def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    await sender()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_nested_helper_media_call_blocks(self):
        source = (
            "def _send(update):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def gallery(update, context):\n"
            "    _send(update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        self.assertIsNotNone(result["candidate"])
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo", result["candidate"])

    def test_ambiguous_unresolved_callable_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    dispatch_table[update.kind](update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_direct_simple_media_call_transforms_cleanly(self):
        source = (
            "def gallery(update, context):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def video_gallery(update, context):\n"
            "    update.message.reply_video(open('x.mp4','rb'))\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo(", result["candidate"])
        self.assertIn("reply_text", result["candidate"])


# ---------------------------------------------------------------------------
# Correction B: deterministic repeat with agreed API
# ---------------------------------------------------------------------------

class DeterministicRepeatTests(unittest.TestCase):
    def test_deterministic_transform_passes(self):
        source = "def gallery(update, context):\n    update.message.reply_photo(1)\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source, args=(), repeats=10)
        self.assertTrue(measurement["deterministic"])
        self.assertEqual(measurement["repeats"], 10)

    def test_deterministic_transform_passes_with_source_kwarg(self):
        source = "def gallery(update, context): pass\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source=source, repeats=10)
        self.assertTrue(measurement["deterministic"])

    def _nondeterministic_random_content(self, source):
        return {"candidate": source + f"# {random.random()}", "status": "OK", "reasons": []}

    def _nondeterministic_time(self, source):
        return {"candidate": source + f"# {time.time()}", "status": "OK", "reasons": []}

    def _nondeterministic_uuid(self, source):
        return {"candidate": source + f"# {uuid.uuid4().hex}", "status": "OK", "reasons": []}

    def _nondeterministic_unordered_set(self, source):
        s = {random.randint(0, 10**9) for _ in range(5)}
        return {"candidate": source + f"# {sorted(s) if random.random() > 2 else list(s)}", "status": "OK", "reasons": []}

    def _nondeterministic_metadata(self, source):
        return {"candidate": source, "status": "OK", "reasons": [f"seen_at:{time.time()}"]}

    def test_nondeterministic_transform_blocks(self):
        source = "x = 1\n"
        variants = [
            self._nondeterministic_random_content,
            self._nondeterministic_time,
            self._nondeterministic_uuid,
            self._nondeterministic_unordered_set,
            self._nondeterministic_metadata,
        ]
        for variant in variants:
            measurement = measure_deterministic_repeat(variant, source, args=(), repeats=10)
            self.assertFalse(measurement["deterministic"], variant.__name__)
            forced_status, unmet = evaluate_gate_a({
                **{k: {"status": "OK"} for k in gate_a.REQUIRED_PREDICATES},
                "deterministic_repeat_all_transforms": {"status": "BLOCKED", "failures": [variant.__name__]},
            })
            self.assertEqual(forced_status, "BLOCKED")
            self.assertIn("deterministic_repeat_all_transforms", unmet)


# ---------------------------------------------------------------------------
# Correction C: real, honest overflow test with production default preserved
# ---------------------------------------------------------------------------

class SiteInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ["index.html", "katalog.html", "UA-0001.html"]:
            with open(os.path.join(self.tmp.name, name), "w") as fh:
                fh.write("<html></html>")

    def test_production_default_max_is_32(self):
        self.assertEqual(DEFAULT_MAX_FILES_PER_ROOT, 32)

    def test_overflow_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "overflow")
        self.assertEqual(result["matched_count"], 3)

    def test_exact_boundary_n_passes(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=3)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["matched_count"], 3)

    def test_boundary_n_plus_one_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")

    def test_default_production_cap_accepts_up_to_32(self):
        for i in range(2, 10):
            with open(os.path.join(self.tmp.name, f"UA-000{i}.html"), "w") as fh:
                fh.write("<html></html>")
        allowed = list(gate_a.ALLOWED_SITE_NAMES)
        result = scan_bounded_inventory(self.tmp.name, allowed)
        self.assertEqual(result["status"], "OK")
        self.assertLessEqual(result["matched_count"], 32)

    def test_missing_root_blocks(self):
        result = scan_bounded_inventory(os.path.join(self.tmp.name, "nope"), ["index.html"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_symlink_rejected(self):
        target = os.path.join(self.tmp.name, "index.html")
        link = os.path.join(self.tmp.name, "katalog.html")
        os.remove(link)
        os.symlink(target, link)
        result = scan_bounded_inventory(self.tmp.name, ["index.html", "katalog.html"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "symlink_rejected")


# ---------------------------------------------------------------------------
# Publication probe fail-closed behavior
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, code):
        self._code = code

    def getcode(self):
        return self._code


class _FakeOpener:
    def __init__(self, raise_exc=None, response_code=None):
        self.raise_exc = raise_exc
        self.response_code = response_code

    def open(self, req, timeout=5):
        if self.raise_exc is not None:
            raise self.raise_exc
        return _FakeResponse(self.response_code)


class PublicationProbeTests(unittest.TestCase):
    def test_404_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_410_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 410, "gone", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_200_blocks(self):
        opener = _FakeOpener(response_code=200)
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_redirect_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 302, "redir", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_network_error_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.URLError("connection refused"))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_non_https_blocks(self):
        result = check_ua0009_not_public("http://example.com/UA-0009.html")
        self.assertEqual(result["status"], "BLOCKED")

    def test_missing_url_blocks(self):
        result = check_ua0009_not_public("")
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# CrossProcessLock stress test (aggregate >=100 contention attempts)
# ---------------------------------------------------------------------------

def _contender_worker(lock_path, start_barrier, result_queue, hold_event):
    guard = CrossProcessLock(lock_path)
    start_barrier.wait()
    acquired = guard.acquire()
    result_queue.put((os.getpid(), acquired))
    if acquired:
        hold_event.wait(timeout=5)
        guard.release()


class CrossProcessLockStressTests(unittest.TestCase):
    def test_simultaneous_stale_takeover_only_one_wins(self):
        ctx = multiprocessing.get_context("fork") if hasattr(multiprocessing, "get_context") else multiprocessing
        rounds = 25
        contenders_per_round = 4
        for round_idx in range(rounds):
            with tempfile.TemporaryDirectory() as tmp:
                lock_path = os.path.join(tmp, "test.lock")
                with open(lock_path, "w") as fh:
                    fh.write(f"999999|stale|deadtoken|{time.time() - 100000}\n")
                start_barrier = ctx.Barrier(contenders_per_round)
                result_queue = ctx.Queue()
                hold_event = ctx.Event()
                procs = [
                    ctx.Process(target=_contender_worker, args=(lock_path, start_barrier, result_queue, hold_event))
                    for _ in range(contenders_per_round)
                ]
                for p in procs:
                    p.start()
                results = [result_queue.get(timeout=10) for _ in procs]
                hold_event.set()
                for p in procs:
                    p.join(timeout=10)
                winners = [r for r in results if r[1]]
                self.assertEqual(len(winners), 1, f"round {round_idx}: {results}")

    def test_release_then_fresh_contender_can_acquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            first = CrossProcessLock(lock_path)
            self.assertTrue(first.acquire())
            first.release()
            second = CrossProcessLock(lock_path)
            self.assertTrue(second.acquire())
            second.release()

    def test_idempotent_release_no_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            lock = CrossProcessLock(lock_path)
            self.assertTrue(lock.acquire())
            lock.release()
            lock.release()

    def test_release_after_directory_removed_does_not_raise(self):
        tmp = tempfile.mkdtemp()
        lock_path = os.path.join(tmp, "test.lock")
        lock = CrossProcessLock(lock_path)
        self.assertTrue(lock.acquire())
        import shutil
        shutil.rmtree(tmp)
        lock.release()


# ---------------------------------------------------------------------------
# RebuildQueue and SafeWriter basic behavior
# ---------------------------------------------------------------------------

class RebuildQueueTests(unittest.TestCase):
    def test_burst_coalesces_to_one_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            q = RebuildQueue(lambda: calls.append(1), os.path.join(tmp, "rebuild.lock"))
            statuses = [q.enqueue() for _ in range(5)]
            self.assertIn("accepted", statuses)
            self.assertGreaterEqual(len(calls), 1)

    def test_requires_bound_callback(self):
        with self.assertRaises(ValueError):
            RebuildQueue(None, "/tmp/whatever.lock")


class SafeWriterTests(unittest.TestCase):
    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            with self.assertRaises(ValueError):
                writer.write_text("../escape.txt", "x")

    def test_writes_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            target = writer.write_text("out.txt", "hello")
            with open(target) as fh:
                self.assertEqual(fh.read(), "hello")


# ---------------------------------------------------------------------------
# Correction E: real synthetic end-to-end Gate A
# ---------------------------------------------------------------------------

CLEAN_CARS_UI = (
    "def gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'photos: {count}')\n"
    "def video_gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'videos: {count}')\n"
    "def diag_photo_show(update, context):\n"
    "    update.message.reply_text('diag photo text')\n"
    "def diag_video_show(update, context):\n"
    "    update.message.reply_text('diag video text')\n"
    "def count_media(update):\n"
    "    return len(update.media)\n"
    "def upload_media(path, data):\n"
    "    with open(path, 'wb') as fh:\n"
    "        fh.write(data)\n"
    "    return True\n"
    "def delete_media(path):\n"
    "    import os as _os\n"
    "    _os.remove(path)\n"
    "    return True\n"
)

CLEAN_USERCUSTOMIZE = "import sys\n\n\ndef _noop():\n    return None\n"

CLEAN_AVTOPEREDACHA = (
    "import sqlite3\n"
    "import time\n"
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)

DB_FUNCTION_SOURCE = (
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)


class EndToEndGateATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.required_input_paths = []
        for name in ["usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
                     "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py"]:
            p = os.path.join(self.tmp.name, name)
            with open(p, "w") as fh:
                fh.write("# fixture\n")
            self.required_input_paths.append(p)

        self.db_path = os.path.join(self.tmp.name, "crm.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()
        self.required_input_paths.append(self.db_path)

        self.backup_archive = os.path.join(self.tmp.name, "backup.tar.gz")
        with open(self.backup_archive, "wb") as fh:
            fh.write(b"fixture-backup-bytes")
        self.backup_sha256 = gate_a._sha256_file(self.backup_archive)

        self.site_root = os.path.join(self.tmp.name, "site")
        os.makedirs(self.site_root)
        with open(os.path.join(self.site_root, "index.html"), "w") as fh:
            fh.write("<html></html>")
        with open(os.path.join(self.site_root, "katalog.html"), "w") as fh:
            fh.write("<html></html>")

        self.run_dir = os.path.join(self.tmp.name, "run")

        fp = {"a": 1}
        self.fixture = {
            "required_inputs": self.required_input_paths,
            "backup_archive": self.backup_archive,
            "backup_archive_sha256": self.backup_sha256,
            "cars_ui_source": CLEAN_CARS_UI,
            "usercustomize_source": CLEAN_USERCUSTOMIZE,
            "avtoperedacha_source": CLEAN_AVTOPEREDACHA,
            "protected_fingerprints_before": fp,
            "protected_fingerprints_after": dict(fp),
            "db_path": self.db_path,
            "ua0009_fingerprint_before": {"h": "same"},
            "ua0009_fingerprint_after": {"h": "same"},
            "ua0009_url": "https://example.com/UA-0009.html",
            "ua0009_opener": _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None)),
            "site_root": self.site_root,
            "allowed_site_names": ["index.html", "katalog.html"],
            "protected_function_names": ["upload_media", "delete_media"],
            "tmp_dir": self.tmp.name,
            "db_function_source": DB_FUNCTION_SOURCE,
            "site_before": {"x": 1},
            "site_after": {"x": 1},
            "run_dir": self.run_dir,
        }

    def test_clean_fixture_reaches_pass_awaiting_approval(self):
        receipt = run_gate_a(self.fixture)
        self.assertEqual(receipt["status"], "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", receipt["unmet_predicates"])
        self.assertEqual(receipt["unmet_predicates"], [])
        self.assertEqual(receipt["production_write"], "NO")
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "receipt.json")))

    def test_backup_hash_mismatch_blocks(self):
        bad = dict(self.fixture)
        bad["backup_archive_sha256"] = "0" * 64
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("backup_verified", receipt["unmet_predicates"])

    def test_protected_fingerprint_change_blocks(self):
        bad = dict(self.fixture)
        bad["protected_fingerprints_after"] = {"a": 2}
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("protected_fingerprints_unchanged", receipt["unmet_predicates"])
        self.assertIn("no_production_write", receipt["unmet_predicates"])

    def test_publication_probe_200_blocks(self):
        bad = dict(self.fixture)
        bad["ua0009_opener"] = _FakeOpener(response_code=200)
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("ua0009_not_public", receipt["unmet_predicates"])

    def test_dynamic_dispatch_in_cars_ui_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
            "def upload_media(path, data): return True\n"
            "def delete_media(path): return True\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("admin_routes_text_only", receipt["unmet_predicates"])

    def test_usercustomize_forbidden_import_blocks(self):
        bad = dict(self.fixture)
        bad["usercustomize_source"] = "import team_bot\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("usercustomize_inert", receipt["unmet_predicates"])

    def test_rebuild_subprocess_blocks(self):
        bad = dict(self.fixture)
        bad["avtoperedacha_source"] = "import subprocess\ndef run():\n    subprocess.Popen(['x'])\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("rebuild_queue_bound_no_process_spawn", receipt["unmet_predicates"])

    def test_slow_work_before_close_blocks(self):
        bad = dict(self.fixture)
        bad["db_function_source"] = (
            "def kolonki_cars(conn):\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    time.sleep(0)\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return rows\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("db_closed_before_slow_work", receipt["unmet_predicates"])

    def test_site_inventory_overflow_blocks(self):
        bad = dict(self.fixture)
        bad["allowed_site_names"] = ["index.html", "katalog.html"]
        bad["max_files_per_root"] = 1
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("site_inventory_unchanged", receipt["unmet_predicates"])

    def test_media_persistence_function_removed_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = CLEAN_CARS_UI.replace(
            "def delete_media(path):\n    import os as _os\n    _os.remove(path)\n    return True\n", "")
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("media_persistence_unchanged", receipt["unmet_predicates"])

    def test_missing_input_blocks(self):
        bad = dict(self.fixture)
        bad["required_inputs"] = self.required_input_paths + [os.path.join(self.tmp.name, "missing.py")]
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("inputs_present_and_regular", receipt["unmet_predicates"])


if __name__ == "__main__":
    unittest.main()


```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_crm_speed_gate_a.py
