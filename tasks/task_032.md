# TASK 032 — CRM-SPEED-001 phase B: real launcher, orchestration, manifest and compatibility

## Authority and immutable safety boundary

Continue the owner-approved TASK 030 repair after TASK 031. Work only under `cloud/`. Do not execute Gate A. Do not access PythonAnywhere, /home/Carix, production URLs, or any real network from implementation-time tests. Do not modify Production, CRM, crm.db, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Do not modify `tasks/`.

Every status/report must contain:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

This is reviewable code only. Do not claim READY_FOR_GATE_A or production acceleration. A successful phase status is READY_FOR_CONTROLLER_REVIEW_PHASE_B.

## Controller evidence that must be fixed

TASK 031 committed canonical concurrency primitives. Its new safety tests pass, including 100 multiprocess rounds, live-owner protection, asynchronous queue, hard-link/symlink/race rejection, and compatibility imports.

However full independent discovery on commit c91c9d001bdfcd3a4bfef7392d1fcc6fcfb142b8 produced 93 tests with 1 failure and 11 errors:

1. Eleven existing end-to-end Gate A tests fail because `run_gate_a` passes a not-yet-created synthetic `run_dir` directly to the hardened SafeWriter, which correctly requires an already-existing validated directory.
2. `RebuildQueueTests.test_burst_coalesces_to_one_followup` is racy because the legacy test immediately observes the callback after `enqueue`. Preserve asynchronous behavior: enqueue may wait only for a bounded worker-start/callback-entry acknowledgement, never for callback completion. A slow callback must still prove prompt return.

Fix the architecture, not the assertions. Do not delete, skip, rename or weaken any existing test.

## 1. Real public orchestration entry point

Provide one public injectable entry point used by both the no-argument launcher and tests. Preserve the historical `run_gate_a(fixture)` API as a compatibility adapter, but it must delegate to the same canonical implementation rather than retain a synthetic parallel path.

The entry point must accept an injected configuration and injected HTTPS opener/clock where needed. Tests use only temporary directories and fake openers. No test may access `/home/Carix` or the network.

The production default configuration must contain only the exact bounded paths already present in the canonical specification. Never recursively scan an account.

## 2. Secure run lifecycle

Before constructing SafeWriter:

- acquire one nonblocking exclusive Gate A lock under the validated fixed QA root;
- validate the QA root is an existing regular directory path with no symlink component;
- create exactly one unique run directory beneath that root using an atomic exclusive operation and mode 0700;
- validate its resolved parent and identity;
- pass that already-existing directory to SafeWriter;
- hold the Gate A lock through final receipt/report emission;
- release idempotently on every return/exception path.

Synthetic compatibility fixtures with a requested non-existing `run_dir` must safely create exactly that child directory after validating its parent. They must not weaken SafeWriter by making SafeWriter itself blindly create arbitrary roots.

No writes are allowed outside the unique run directory except validated lock/guard files under the QA root.

## 3. Measured fail-closed phases

The canonical orchestration must emit measured phase records:

- 20: lock, preflight, fixed bounded inputs, free space, backup archive SHA-256, initial fingerprints;
- 40: secure source reads and isolated candidate/diff creation;
- 60: compile candidates together without importing/executing application modules;
- 80: deterministic/structural/concurrency/SQLite/media/publication evidence;
- 100: after-workload fingerprints, site inventories, receipt and report.

Each record includes phase, monotonic start/end, duration and status. 100 means finished, not passed.

Any exception, absent input, unsafe path, ambiguous anchor, missing evidence or failed predicate must produce a complete BLOCKED receipt/report when safe evidence emission remains possible and must cause a nonzero launcher exit.

## 4. No-argument launcher

`RUN_GATE_A_CRM_SPEED.py` must invoke the public orchestration entry point. It must not merely print DEFAULT_CONFIG and return 0.

Requirements:

- no argument path uses only DEFAULT_CONFIG;
- do not import or execute production application modules;
- return 0 only for `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL`;
- return nonzero for BLOCKED or internal failure;
- print a bounded sanitized location/status summary;
- no automatic installation, restart, publication or production mutation.

The repository automation and tests must never execute the no-argument production configuration. Tests monkeypatch/inject a temporary configuration.

## 5. Secure fixed input evidence

Implement secure source reads with no-follow/lstat/fstat identity checks before and after reading. Required inputs must be regular, non-symlink files; directories and hard-linked surprises are BLOCKED. Record canonical path, size, mode, mtime_ns and SHA-256.

Verify free space and exact backup archive SHA-256 before candidate creation.

Fingerprint all protected inputs and each of the three explicitly configured bounded site inventories before the workload, and again only after the full candidate/test workload. Derive unexpected changes from fresh measurements, never from caller-supplied adjacent snapshots.

No recursive account scan. Bounded inventories must block at overflow, unsafe entries, missing required root or ambiguity.

## 6. Manifest and verification

Rewrite `build_manifest.py` and `verify_gate_a.py` as real canonical implementations used by orchestration.

Manifest must deterministically bind:

- package-code hashes;
- secure source fingerprints;
- candidate and unified-diff hashes;
- compilation/test evidence;
- deterministic repetition records;
- SQLite/UA-0009/publication evidence;
- before/after site inventories;
- allowed-write ledger;
- report and receipt-relevant outputs.

Do not follow symlinks. Reject duplicates, missing fields, unsafe paths and non-regular files.

Verification must enumerate a fixed required predicate set. Every absent, false, malformed or non-OK predicate blocks. It must verify receipt/manifest hashes and all bound outputs. No pass from hard-coded booleans, self-referential presence checks, caller-supplied after snapshots or missing evidence.

## 7. Complete receipt/report

Machine-readable receipt and human report must include task ID, timestamps, phase records, package/input/candidate/diff hashes, compilation results, deterministic records, concurrency/structural proofs, SQLite and UA-0009 non-PII evidence placeholders/results, no-redirect publication result, site inventories, synthetic latency marked NON-PRODUCTION, unexpected writes/changes, blockers, next safe action, PRODUCTION_WRITE: NO, and final status.

Until later TASK 033 completes the transform/SQLite/publication implementations, missing real evidence must remain BLOCKED. Do not fabricate PASS merely to make a clean synthetic fixture green if a mandatory mechanism is absent.

## 8. RebuildQueue compatibility without synchronous regression

Adjust the canonical queue only as needed so a newly accepted enqueue can wait for a very short bounded worker/callback-entry acknowledgement. It must not wait for callback completion.

Required behavioral proofs:

- a callback that blocks for 0.20 seconds still yields enqueue return far below callback duration;
- immediate legacy observation after an accepted enqueue deterministically sees callback entry where no competing lock exists;
- burst remains one active plus at most one pending follow-up;
- no per-enqueue worker storm, retry spin or synchronous callback execution in the calling thread.

All TASK 031 safety semantics remain mandatory.

## Mandatory tests

Create `cloud/crm_speed_optimization/test_task_032_orchestration.py`.

Tests must prove:

1. Launcher calls canonical orchestration and propagates PASS/nonzero BLOCKED status; it is not print-only.
2. Synthetic entry point creates exactly one validated run directory before SafeWriter.
3. Missing/symlink/non-regular/hard-link input blocks.
4. Backup hash mismatch blocks before candidate creation.
5. Lock duplicate returns promptly without altering owner evidence.
6. Phase order is exactly 20/40/60/80/100 and durations are measured.
7. Before/after inventories surround the entire workload, not adjacent calls.
8. Candidate files compile together without importing them.
9. Missing required predicate, altered manifest hash, altered candidate/diff/report, or unexpected write blocks.
10. BLOCKED returns nonzero and emits complete bounded evidence when possible.
11. No test touches `/home/Carix` or network.
12. All existing TASK 031 and historical tests remain semantically intact and pass.

Controller target:

`python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'`

## Deliverables

Return complete contents for exactly:

- `cloud/crm_speed_optimization/canonical_modules.py`
- `cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py`
- `cloud/crm_speed_optimization/crm_speed_gate_a.py`
- `cloud/crm_speed_optimization/build_manifest.py`
- `cloud/crm_speed_optimization/verify_gate_a.py`
- `cloud/crm_speed_optimization/test_task_032_orchestration.py`
- `cloud/crm_speed_optimization/TASK_032_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Do not return unrelated files. All implementation must be complete, mutually consistent and Claude-authored. No placeholders, TODO-only behavior, credentials, PII, production imports, or production-write capability.

## Exact current source snapshots


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/canonical_modules.py

```python
"""Canonical implementations shared by the launcher, orchestrator, and
tests for CRM-SPEED-001. This module is the SINGLE source of truth for
CrossProcessLock, SingletonGuard, RebuildQueue, and SafeWriter.

cross_process_lock.py, rebuild_queue.py, safe_writer.py, and
singleton_guard.py are thin re-export/compatibility modules kept only for
backward-compatible imports; they contain no divergent lock logic of
their own.

TASK 031 phase A. No production imports. No production-write capability.
All writes are confined to explicitly supplied, already-existing local
directories (temporary directories in tests).
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

    enqueue() returns promptly. At most one callback is active at a time,
    executed on a single bounded background worker thread. At most one
    pending follow-up is retained for a burst. The rebuild critical
    section is protected by the canonical CrossProcessLock. Callback
    failures are caught, sanitized (truncated) and recorded; there is no
    infinite retry or recursive drain.
    """

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
        self.runs = 0
        self.coalesced = 0
        self.errors = []

    def enqueue(self):
        with self._cv:
            if self._stopped:
                return "stopped"
            if self._running:
                self._pending = True
                self.coalesced += 1
                self._cv.notify_all()
                return "coalesced"
            self._pending = True
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._loop, daemon=True)
                self._worker.start()
            self._cv.notify_all()
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
            acquired = False
            lock = CrossProcessLock(self._lock_path)
            try:
                acquired = lock.acquire()
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

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py

```python
#!/usr/bin/env python3
"""No-argument Gate A launcher artifact.

IMPORTANT: This script is delivered for independent controller/owner
execution on PythonAnywhere ONLY, after review and explicit approval. It is
NEVER executed automatically by Claude/Cloud or by this repository's own
automation. Running this file is a separate, owner-approved action outside
the scope of any cloud/ task.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crm_speed_gate_a import DEFAULT_CONFIG  # noqa: E402


def main():
    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(DEFAULT_CONFIG["run_root"], run_id)
    print("This launcher is a delivered artifact for controller/owner-run execution only.")
    print("Claude/Cloud automation does not execute Gate A against production.")
    print(json.dumps({"planned_run_dir": run_dir, "config": DEFAULT_CONFIG}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

```python
"""CRM-SPEED-001 Gate A orchestration logic (TASK 029 canonical integration).

This module imports canonical mechanisms from canonical_modules.py rather
than redefining them, and now also imports the canonical admin-media
transform/scanner from cars_ui_transform.py instead of redefining a
duplicate legacy transformer/scanner. scan_reachable_call_graph and
transform_cars_ui below are thin adapters around cars_ui_transform:

- scan_reachable_call_graph(source, entry_points, max_depth=25) parses
  `source`, delegates to cars_ui_transform.scan_reachable_call_graph for
  the actual reachable call-graph analysis, translates a small number of
  flag names into the historical vocabulary this module's callers and
  test suite expect (for example "dynamic_dispatch_forbidden:getattr"),
  filters out unresolved-callable flags for the small SAFE_BUILTIN_NAMES
  allowlist (len/str/int/... - matching the historical permissive
  treatment of ordinary builtins), and returns (clean, violations).
- transform_cars_ui(source, entry_points=None) first uses the adapter
  scan to decide whether any dynamic/ambiguous construct is present
  (fail closed, BLOCKED) or whether there is nothing to rewrite (OK,
  candidate=source unchanged), and only delegates the actual atomic
  media-call rewriting to cars_ui_transform.transform_cars_ui when there
  is at least one direct media call and no dynamic violation. The
  canonical result is then translated into this module's historical
  {'candidate', 'status', 'reasons'} shape.

Gate A is never executed against production by this repository. Every
function here operates only on strings/bytes/paths explicitly supplied by
the caller (production launcher or test fixture).
"""
import os
import ast
import stat
import json
import time
import hashlib
import difflib
import sqlite3
import urllib.request
import urllib.error

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
import cars_ui_transform

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
    """Historically this module allowlisted plain builtin calls (len,
    str, sorted, ...) as not being dynamic-dispatch violations. The
    canonical cars_ui_transform scanner is stricter (it flags every call
    that does not resolve to a module-level function or getattr as an
    unresolved_callable, including ordinary builtins), so this adapter
    filters that specific, narrow, pre-approved allowlist back out when
    translating canonical flags into this module's violation list."""
    if flag.startswith("unresolved_callable:"):
        parts = flag.split(":")
        name = parts[1] if len(parts) > 1 else ""
        return name in SAFE_BUILTIN_NAMES
    return False


def _translate_dynamic_flag(flag):
    """Translate a small number of canonical flag names into the
    historical vocabulary this module's callers/tests expect."""
    if flag.startswith("getattr_dispatch"):
        return "dynamic_dispatch_forbidden:getattr"
    return flag


def scan_reachable_call_graph(source, entry_points, max_depth=25):
    """Thin adapter: parses `source` and delegates the reachable
    call-graph analysis to cars_ui_transform.scan_reachable_call_graph.
    Returns (clean, violations) exactly as the historical API did.
    `max_depth` is accepted for backward API compatibility; the
    canonical scanner bounds recursion via its own visited-set closure
    and does not require an explicit depth cap for the fixtures used by
    this package.
    """
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
    """Thin adapter around cars_ui_transform.transform_cars_ui.

    Fails closed exactly as the historical API did:
    - if the original reachable call graph (via the adapter scan above)
      contains any dynamic/ambiguous construct, the candidate is None
      and status is BLOCKED;
    - if there are no violations at all (no dynamic issues and no direct
      media calls), the entry points are already text-only and the
      original source is returned unchanged with status OK;
    - otherwise (only direct_media_call violations present, no dynamic
      flags) the actual atomic media-call rewrite is delegated to
      cars_ui_transform.transform_cars_ui, and the canonical result is
      translated into this module's {'candidate','status','reasons'}
      shape. The transformed graph is re-scanned; any remaining
      violation also yields candidate None / BLOCKED.
    """
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


# ---------------------------------------------------------------------------
# Correction B: deterministic repeat, one explicit signature
# ---------------------------------------------------------------------------

def _stable_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def measure_deterministic_repeat(transform_fn, source, args=(), repeats=10):
    """Run transform_fn(source, *args) `repeats` times from the exact same
    original source and compare candidate bytes, unified-diff bytes,
    status, reason list, and a metadata digest across all repetitions.
    transform_fn must return a dict with keys 'candidate', 'status',
    'reasons'. Returns a dict with 'deterministic' (bool), 'repeats', and
    the full list of per-repetition records."""
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


# ---------------------------------------------------------------------------
# Correction C: bounded site/public inventory with test-only max override
# ---------------------------------------------------------------------------

def scan_bounded_inventory(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    """Non-recursive bounded scan of `root` for entries in `allowed_names`.
    Production callers must use the default max_files_per_root=32. Tests
    may pass a smaller value explicitly to construct real overflow cases
    without lowering the production default."""
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


# ---------------------------------------------------------------------------
# Publication probe -- fails closed on every network ambiguity
# ---------------------------------------------------------------------------

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_ua0009_not_public(url, opener=None):
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


# ---------------------------------------------------------------------------
# Remaining Gate A predicate checks (evidence-derived, no fabricated True)
# ---------------------------------------------------------------------------

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


def evaluate_gate_a(evidence):
    """Derive final status only from measured evidence. No predicate may
    default to True. Missing/failed evidence -> BLOCKED."""
    unmet = []
    for key in REQUIRED_PREDICATES:
        item = evidence.get(key)
        if not isinstance(item, dict) or item.get("status") != "OK":
            unmet.append(key)
    if unmet:
        return "BLOCKED", unmet
    return "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", []


def run_gate_a(fixture):
    """Single, real, executable orchestration entry point. `fixture` supplies
    every bounded input needed for one full Gate A evaluation (production
    launcher builds it from DEFAULT_CONFIG bound to real /home/Carix paths;
    tests pass a synthetic fixture). This repository never invokes this
    function against production; GATE_A_EXECUTED remains NO for every task
    delivered under cloud/."""
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

    status, unmet = evaluate_gate_a(evidence)
    receipt = {
        "status": status,
        "unmet_predicates": unmet,
        "evidence": evidence,
        "production_write": "NO",
        "generated_at": time.time(),
    }
    if fixture.get("run_dir"):
        writer = SafeWriter(fixture["run_dir"])
        writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
    return receipt

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/build_manifest.py

```python
"""Builds a deterministic manifest of package code hashes and run output
hashes for one Gate A run. Read-only against the package directory; writes
only when explicitly invoked with a run directory to inspect."""
import os
import sys
import json
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(package_dir, run_dir=None):
    manifest = {"package_files": {}, "run_outputs": {}}
    for name in sorted(os.listdir(package_dir)):
        full = os.path.join(package_dir, name)
        if name.endswith(".py") and os.path.isfile(full):
            manifest["package_files"][name] = _sha256_file(full)
    if run_dir and os.path.isdir(run_dir):
        for root, _dirs, files in os.walk(run_dir):
            for name in sorted(files):
                path = os.path.join(root, name)
                manifest["run_outputs"][os.path.relpath(path, run_dir)] = _sha256_file(path)
    return manifest


if __name__ == "__main__":
    package_dir = os.path.dirname(os.path.abspath(__file__))
    run_dir = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(build_manifest(package_dir, run_dir), indent=2))

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/build_manifest.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/verify_gate_a.py

```python
"""Read-only verification of a Gate A receipt. Does not execute Gate A and
does not touch production."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VALID_STATUSES = ("GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", "BLOCKED")


def verify_receipt(receipt_path):
    with open(receipt_path, "r") as fh:
        receipt = json.load(fh)
    if receipt.get("production_write") != "NO":
        return False, "production_write_not_declared_no"
    if receipt.get("status") not in VALID_STATUSES:
        return False, f"unexpected_status:{receipt.get('status')}"
    if receipt.get("status") == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL" and receipt.get("unmet_predicates"):
        return False, "pass_status_with_unmet_predicates"
    return True, "ok"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: verify_gate_a.py <receipt.json>")
        sys.exit(2)
    ok, reason = verify_receipt(sys.argv[1])
    print(json.dumps({"ok": ok, "reason": reason}))
    sys.exit(0 if ok else 1)

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/verify_gate_a.py

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
