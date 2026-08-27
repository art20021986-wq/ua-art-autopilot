"""Canonical implementations shared by the launcher, orchestrator, and
tests for CRM-SPEED-001. This module is the SINGLE source of truth for
CrossProcessLock, SingletonGuard, RebuildQueue, and SafeWriter.

cross_process_lock.py, rebuild_queue.py, safe_writer.py, and
singleton_guard.py are thin re-export/compatibility modules kept only for
backward-compatible imports; they contain no divergent lock logic of
their own.

TASK 031/032. TASK 038 corrected RebuildQueue._loop to enclose lock
construction/acquisition/callback/release/state-cleanup in one complete
exception boundary so that no exception can ever escape to
threading.excepthook, with no retry/spin on failure.

TASK 041: callback failures now record only a bounded sanitized category
("CallbackError:<ExceptionClass>") instead of str(exc), which could leak
PII, tokens, paths, or DB values into evidence/logs. The optional error
handler still receives the raw exception object so callers may perform
their own sanitized handling, but nothing persisted/returned/logged by
RebuildQueue itself ever contains raw exception text.

No production imports. No production-write capability. All writes are
confined to explicitly supplied, already-existing local directories
(temporary directories in tests, or a validated already-existing run
directory created by crm_speed_gate_a.orchestrate_gate_a).
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
    worker/callback-entry acknowledgement (the worker has attempted to
    acquire the rebuild lock and is about to invoke the callback, or has
    failed to do so cleanly) -- it never waits for the callback itself to
    finish. At most one callback is active at a time, executed on a
    single bounded background worker thread. At most one pending
    follow-up is retained for a burst. The rebuild critical section is
    protected by the canonical CrossProcessLock.

    TASK 038 correction: lock construction, acquisition, callback
    invocation, release, and worker-state cleanup are now enclosed in one
    complete exception boundary. If the lock parent disappears or lock
    construction/acquisition fails, the pending acknowledgement event is
    still set, one bounded sanitized error (exception class name only) is
    recorded, running/pending state is cleared safely, waiters are
    notified, and that worker iteration terminates without retry or
    spin. No exception can reach threading.excepthook.

    TASK 041 correction: callback failures now record only
    "CallbackError:<ExceptionClass>" -- never str(exc), which could
    contain PII, tokens, filesystem paths, or DB values. The optional
    error_handler still receives the raw exception object for callers
    that need it, but that raw text is never stored on this queue.
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
            lock = None
            try:
                try:
                    lock = CrossProcessLock(self._lock_path)
                    acquired = lock.acquire()
                except Exception as exc:
                    sanitized = type(exc).__name__
                    with self._cv:
                        self.errors.append(sanitized)
                    acquired = False
                finally:
                    # The worker-entry acknowledgement fires whether or
                    # not the lock could be constructed/acquired, so
                    # enqueue() never waits past this point.
                    if ack_event is not None:
                        ack_event.set()
                if acquired:
                    try:
                        self._callback()
                        with self._cv:
                            self.runs += 1
                    except Exception as exc:
                        sanitized = "CallbackError:" + type(exc).__name__
                        with self._cv:
                            self.errors.append(sanitized)
                        if self._error_handler is not None:
                            try:
                                self._error_handler(exc)
                            except Exception:
                                pass
            except Exception as exc:
                # Absolute fail-safe boundary. Nothing below this may
                # ever escape to threading.excepthook.
                sanitized = type(exc).__name__
                with self._cv:
                    self.errors.append(sanitized)
            finally:
                if acquired and lock is not None:
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
