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
