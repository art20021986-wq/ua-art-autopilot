# TASK 031 — CRM-SPEED-001 phase A: canonical concurrency and secure writer

## Authority and immutable safety boundary

Continue the owner-approved TASK 030 repair in small, independently committable phases because the monolithic TASK 030 response was correctly rejected when two required files were missing. This phase implements only the canonical concurrency primitives and secure writer.

Work only under `cloud/`. Do not execute Gate A. Do not access PythonAnywhere or the network. Do not modify Production, CRM, crm.db, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Do not modify `tasks/`. The result is reviewable code and offline tests only.

Every status/report must state exactly:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Context and non-regression rule

The controller independently proved the current package compiles and the previous 73-test suite passes, but executable negative probes exposed unsafe lock takeover, synchronous queue execution, hard-link acceptance, and incomplete lifecycle behavior. Preserve all existing public imports and APIs used by the current suite. Do not delete, skip, rename, weaken, or rewrite existing tests merely to obtain green. Thin compatibility modules must continue to re-export the single canonical implementation.

TASK 031 is an intermediate phase. Do not claim READY_FOR_GATE_A or production acceleration. The only truthful successful phase status is READY_FOR_CONTROLLER_REVIEW_PHASE_A.

## Mandatory implementation

### 1. CrossProcessLock

Implement one canonical Linux-safe nonblocking cross-process lock in `canonical_modules.py`.

Requirements:

- Validate that the lock path and guard path remain inside their already-existing validated parent; never create a deleted parent during release.
- Serialize owner inspection, stale takeover, acquisition and release with `fcntl.flock(LOCK_EX | LOCK_NB)` on a validated regular guard file. Re-read owner evidence only while serialized. No blind unlink/read/unlink TOCTOU.
- Owner evidence must include PID, Linux process-start identity from `/proc/<pid>/stat`, a cryptographically random ownership token, and acquisition timestamp.
- A live PID with the same process-start identity must never be stolen merely because the record is old.
- PID missing or process-start mismatch may be treated as stale only while holding the guard serialization lock and after re-reading the evidence.
- Unknown liveness/identity must fail closed; never positively declare stale from missing evidence alone.
- A simultaneous duplicate acquisition returns `False` promptly and never changes owner evidence.
- Only the matching token may release the owner record.
- Release and atexit cleanup are idempotent, exception-safe, never kill a process, never recreate deleted parents, and never raise.
- Preserve constructor/acquire/release behavior expected by existing callers. Context-manager helpers may be added without breaking compatibility.

### 2. SingletonGuard

Implement SingletonGuard on the exact same canonical lock semantics, with:

- explicit lifecycle installation, not import-time startup;
- idempotent cleanup;
- normal return, exception and atexit release;
- supported-signal cleanup without overwriting unrelated handlers irreversibly;
- immediate duplicate diagnostic/result;
- no process killing and no production imports.

`singleton_guard.py` may provide compatibility helpers but must delegate to the canonical class instead of carrying divergent lock logic.

### 3. RebuildQueue

Implement a truly asynchronous bounded coalescing queue:

- callback is mandatory and callable;
- `enqueue()` returns promptly while a slow callback executes in one bounded worker thread;
- no per-enqueue thread/process creation and no unbounded thread/process storm;
- at most one active callback and at most one pending follow-up for a burst;
- use the canonical CrossProcessLock around the rebuild critical section;
- callback failures are caught, sanitized and recorded; no infinite retry, spin or recursive drain;
- provide deterministic bounded shutdown/join behavior for tests without making handler enqueue block;
- preserve existing public return values where practical and provide bounded observable counters/state for tests.

### 4. SafeWriter

Harden SafeWriter so every write is confined to the resolved existing run directory:

- reject absolute paths, traversal and path escape;
- reject symlink in every parent;
- reject target symlink, non-regular target and hard-link target (`st_nlink != 1`);
- reject an unsafe or replaced parent/target during identity re-check;
- use an exclusive restrictive temporary file in the validated target directory;
- use no-follow flags where available and validate with `fstat`;
- fsync file and directory;
- atomic replace only after all checks;
- do not silently create an attacker-controlled parent chain;
- remove temporary files safely on error;
- maintain an exact allowed-write ledger including relative path, size and SHA-256;
- expose no production-write capability.

## Mandatory executable tests

Create `cloud/crm_speed_optimization/test_task_031_concurrency.py` with offline deterministic tests that execute the real canonical classes.

Required cases:

1. A live owner with matching PID/start identity remains owner even when `stale_after_seconds` has expired.
2. Dead owner stale takeover.
3. PID reuse/start mismatch takeover.
4. Unknown identity fails closed.
5. Foreign token cannot release.
6. Release, double release, exception cleanup, atexit cleanup and deleted-parent cleanup never raise or recreate parents.
7. Deterministic multiprocess barrier: at least 100 high-contention takeover/acquisition rounds, exactly one winner per round, held until every contender has attempted.
8. Slow callback proves `enqueue()` returns promptly before callback completes.
9. Burst produces one active run and at most one coalesced follow-up.
10. Rebuild callback exception is bounded; no spin or infinite retry.
11. Symlink parent, target symlink, hard-link target, non-regular target, traversal, absolute path and deleted parent are rejected.
12. Target/parent replacement race is deterministically injected and rejected.
13. Successful SafeWriter write is atomic, restrictive, hash-recorded and byte-exact.
14. Compatibility imports from `cross_process_lock.py`, `rebuild_queue.py`, `safe_writer.py` and `singleton_guard.py` resolve to the canonical implementations.

Tests must use only temporary directories, local processes and local threads. No network. No `/home/Carix`. No sleeps longer than needed for deterministic synchronization.

Target controller command:

`python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'`

## Deliverables

Return complete contents for exactly these phase deliverables:

- `cloud/crm_speed_optimization/canonical_modules.py`
- `cloud/crm_speed_optimization/cross_process_lock.py`
- `cloud/crm_speed_optimization/rebuild_queue.py`
- `cloud/crm_speed_optimization/safe_writer.py`
- `cloud/crm_speed_optimization/singleton_guard.py`
- `cloud/crm_speed_optimization/test_task_031_concurrency.py`
- `cloud/crm_speed_optimization/TASK_031_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Do not return unrelated files. All Python files must contain complete implementations, compile, and contain no placeholders, TODO-only code, credentials, PII, production imports or production-write capability.

`cloud/latest_status.md` and `cloud/owner_reply.md` must state that this is phase A only, Production is untouched, Gate A was not executed, and later phases plus independent controller review remain required.

Final Claude status is DONE only when all listed files are complete. Summary status inside the reports is READY_FOR_CONTROLLER_REVIEW_PHASE_A, never READY_FOR_GATE_A.

## Exact current source snapshots


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/canonical_modules.py

```python
"""Canonical implementations shared by the launcher, orchestrator, and
tests for CRM-SPEED-001. This module is the SINGLE source of truth for
CrossProcessLock, SingletonGuard, RebuildQueue, and SafeWriter.

crm_speed_gate_a.py MUST import these classes directly. It must never
redefine or shadow them. cross_process_lock.py, rebuild_queue.py, and
safe_writer.py are thin re-export modules kept only for backward-compatible
imports; they contain no logic of their own.
"""
import os
import time
import uuid
import atexit
import tempfile
import threading


def _process_start_time(pid):
    """Best-effort process start-time fingerprint using /proc (Linux).
    Returns None when unavailable; callers must treat None as unknown and
    must not use it to positively confirm liveness."""
    try:
        with open(f"/proc/{pid}/stat", "r") as fh:
            data = fh.read()
        end = data.rfind(')')
        rest = data[end + 2:].split()
        return rest[19]
    except Exception:
        return None


class LockEvidence:
    def __init__(self, pid, start_time, token, acquired_at):
        self.pid = pid
        self.start_time = start_time
        self.token = token
        self.acquired_at = acquired_at

    def to_line(self):
        return f"{self.pid}|{self.start_time}|{self.token}|{self.acquired_at}\n"

    @staticmethod
    def parse(line):
        parts = line.strip().split("|")
        if len(parts) != 4:
            return None
        pid, start_time, token, acquired_at = parts
        try:
            return LockEvidence(int(pid), start_time, token, float(acquired_at))
        except ValueError:
            return None


class CrossProcessLock:
    """Atomic, non-blocking, cross-process lock with PID + process-start
    evidence, an ownership token, safe stale takeover, and idempotent,
    exception-safe release. Never kills another process."""

    def __init__(self, path, stale_after_seconds=300):
        self.path = path
        self.stale_after_seconds = stale_after_seconds
        self.token = uuid.uuid4().hex
        self._owned = False
        self._atexit_registered = False

    def _read(self):
        try:
            with open(self.path, "r") as fh:
                return LockEvidence.parse(fh.readline())
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _is_live(self, evidence):
        if evidence is None:
            return False
        try:
            os.kill(evidence.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False
        current_start = _process_start_time(evidence.pid)
        if current_start is not None and evidence.start_time not in (None, "", current_start):
            return False
        if time.time() - evidence.acquired_at > self.stale_after_seconds:
            return False
        return True

    def acquire(self):
        """Return True only if this instance now owns the lock."""
        existing = self._read()
        if existing is not None and self._is_live(existing):
            return False
        fd = None
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            existing = self._read()
            if existing is not None and self._is_live(existing):
                return False
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return False
        evidence = LockEvidence(os.getpid(), _process_start_time(os.getpid()) or "", self.token, time.time())
        with os.fdopen(fd, "w") as fh:
            fh.write(evidence.to_line())
            fh.flush()
            os.fsync(fh.fileno())
        recheck = self._read()
        if recheck is None or recheck.token != self.token:
            return False
        self._owned = True
        if not self._atexit_registered:
            atexit.register(self.release)
            self._atexit_registered = True
        return True

    def release(self):
        if not self._owned:
            return
        try:
            current = self._read()
            if current is not None and current.token == self.token:
                try:
                    os.unlink(self.path)
                except FileNotFoundError:
                    pass
        except Exception:
            pass
        finally:
            self._owned = False


class SingletonGuard(CrossProcessLock):
    """Process singleton built directly on CrossProcessLock semantics."""
    pass


class RebuildQueue:
    """Bounded coalescing rebuild queue. At most one pending follow-up is
    kept while a rebuild is running. enqueue() returns immediately."""

    def __init__(self, callback, lock_path):
        if callback is None or not callable(callback):
            raise ValueError("RebuildQueue requires an explicit bound callable callback")
        self._callback = callback
        self._lock = CrossProcessLock(lock_path)
        self._pending = False
        self._running = False
        self._guard = threading.Lock()
        self.runs = 0
        self.coalesced = 0

    def enqueue(self):
        with self._guard:
            if self._running:
                self._pending = True
                self.coalesced += 1
                return "coalesced"
            self._pending = True
        self._drain()
        return "accepted"

    def _drain(self):
        while True:
            with self._guard:
                if not self._pending or self._running:
                    return
                self._pending = False
                self._running = True
            acquired = self._lock.acquire()
            try:
                if acquired:
                    self._callback()
                    self.runs += 1
            finally:
                with self._guard:
                    self._running = False
                if acquired:
                    self._lock.release()


class SafeWriter:
    """Writes only regular files inside a resolved run directory. Rejects
    traversal/symlink surprises and writes atomically with fsync."""

    def __init__(self, run_dir):
        self.run_dir = os.path.realpath(run_dir)
        os.makedirs(self.run_dir, exist_ok=True)

    def _resolve(self, relative_path):
        target = os.path.realpath(os.path.join(self.run_dir, relative_path))
        if not (target == self.run_dir or target.startswith(self.run_dir + os.sep)):
            raise ValueError("path escapes run directory")
        return target

    def write_text(self, relative_path, content):
        target = self._resolve(relative_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(target))
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass
        dir_fd = os.open(os.path.dirname(target), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        except Exception:
            pass
        finally:
            os.close(dir_fd)
        return target

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/canonical_modules.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/cross_process_lock.py

```python
"""Thin re-export of the canonical CrossProcessLock implementation.

This module contains no logic. Historical callers/tests that import from
here receive the exact same class object as canonical_modules and
crm_speed_gate_a. Do not add logic to this file.
"""
from canonical_modules import CrossProcessLock, LockEvidence, SingletonGuard

__all__ = ["CrossProcessLock", "LockEvidence", "SingletonGuard"]

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/cross_process_lock.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/rebuild_queue.py

```python
"""Thin re-export of the canonical RebuildQueue implementation.

This module contains no logic of its own; it exists only so historical
imports keep resolving to the exact same object used by the launcher and
orchestrator.
"""
from canonical_modules import RebuildQueue

__all__ = ["RebuildQueue"]

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/rebuild_queue.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/safe_writer.py

```python
"""Thin re-export of the canonical SafeWriter implementation."""
from canonical_modules import SafeWriter

__all__ = ["SafeWriter"]

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/safe_writer.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/singleton_guard.py

```python
"""
singleton_guard.py

Process singleton guard built on CrossProcessLock. A duplicate start
exits quickly with a defined nonzero diagnostic code and never disturbs
another process's lock. Release is guaranteed via CrossProcessLock's own
atexit registration plus signal handling installed here.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cross_process_lock import CrossProcessLock  # noqa: E402

DUPLICATE_START_EXIT_CODE = 78


def acquire_singleton_or_exit(lock_path: str, label: str) -> CrossProcessLock:
    lock = CrossProcessLock(lock_path, label=label)
    if not lock.try_acquire():
        sys.stderr.write(
            f"[singleton_guard] {label}: another live instance already holds "
            f"{lock_path}; refusing to start (exit {DUPLICATE_START_EXIT_CODE}).\n"
        )
        sys.exit(DUPLICATE_START_EXIT_CODE)
    lock.install_signal_handlers()
    return lock

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/singleton_guard.py
