"""
cross_process_lock.py

Atomic, non-blocking, cross-process lock with PID + process-start-time
evidence, an ownership token, safe stale-lock takeover, and owner-only
release. No process is ever killed.

All lock mutation (read -> decide stale/live -> write) is guarded by an
OS-level fcntl.flock() critical section on a companion ".guard" file, so
the decision is not subject to TOCTOU races between independent
processes. try_acquire() never blocks: if the guard is momentarily busy
it returns False immediately rather than waiting.

This module performs no network, database, or subprocess activity and
logs nothing containing secrets.
"""
from __future__ import annotations

import atexit
import errno
import fcntl
import json
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Optional


class LockError(Exception):
    pass


class LockHeldByLiveProcess(LockError):
    pass


def _read_proc_start_time(pid: int) -> Optional[int]:
    """Best-effort Linux /proc start-time (field 22 of /proc/<pid>/stat).

    Returns None when /proc is unavailable or the process cannot be
    inspected. A None result means liveness cannot be proven by
    start-time alone and callers must treat the PID conservatively
    (i.e. as live, to avoid a false stale takeover).
    """
    try:
        with open(f"/proc/{pid}/stat", "r") as fh:
            raw = fh.read()
        end = raw.rfind(")")
        fields = raw[end + 2:].split()
        return int(fields[19])
    except Exception:
        return None


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        return False
    return True


@dataclass
class LockPayload:
    pid: int
    start_time: Optional[int]
    token: str
    created_at: float
    label: str

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True)

    @staticmethod
    def from_json(raw: str) -> "LockPayload":
        data = json.loads(raw)
        return LockPayload(**data)


class CrossProcessLock:
    """Atomic cross-process mutual-exclusion lock.

    Usage::

        lock = CrossProcessLock("/path/to/x.lock", label="rebuild")
        if lock.try_acquire():
            try:
                ...critical section...
            finally:
                lock.release()
    """

    def __init__(self, lock_path: str, label: str = "lock"):
        self.lock_path = lock_path
        self.guard_path = lock_path + ".guard"
        self.label = label
        self.token = uuid.uuid4().hex
        self._held = False
        self._registered_atexit = False

    def _payload_is_live(self, payload: LockPayload) -> bool:
        if not _pid_exists(payload.pid):
            return False
        current_start = _read_proc_start_time(payload.pid)
        if payload.start_time is None or current_start is None:
            return True
        return current_start == payload.start_time

    def _with_guard(self, fn, nonblocking: bool = True):
        guard_fd = os.open(self.guard_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
            try:
                fcntl.flock(guard_fd, flags)
            except BlockingIOError:
                return None, False
            try:
                return fn(), True
            finally:
                fcntl.flock(guard_fd, fcntl.LOCK_UN)
        finally:
            os.close(guard_fd)

    def _read_existing(self) -> Optional[LockPayload]:
        try:
            with open(self.lock_path, "r") as fh:
                raw = fh.read()
            return LockPayload.from_json(raw)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def _write_payload_atomic(self, payload: LockPayload) -> None:
        tmp_path = f"{self.lock_path}.{self.token}.tmp"
        fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, payload.to_json().encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp_path, self.lock_path)
        dir_path = os.path.dirname(os.path.abspath(self.lock_path)) or "."
        dir_fd = os.open(dir_path, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def try_acquire(self) -> bool:
        """Non-blocking. Returns True iff this process now owns the lock."""

        def _attempt():
            existing = self._read_existing()
            if existing is not None and self._payload_is_live(existing):
                return False
            payload = LockPayload(
                pid=os.getpid(),
                start_time=_read_proc_start_time(os.getpid()),
                token=self.token,
                created_at=time.time(),
                label=self.label,
            )
            self._write_payload_atomic(payload)
            return True

        result, ran = self._with_guard(_attempt, nonblocking=True)
        if not ran:
            self._held = False
            return False
        self._held = bool(result)
        if self._held and not self._registered_atexit:
            atexit.register(self.release)
            self._registered_atexit = True
        return self._held

    def owned_by_me(self) -> bool:
        existing = self._read_existing()
        return bool(existing and existing.token == self.token and existing.pid == os.getpid())

    def release(self) -> bool:
        if not self._held:
            return False

        def _attempt():
            existing = self._read_existing()
            if existing is None:
                return True
            if existing.token != self.token or existing.pid != os.getpid():
                return False
            try:
                os.remove(self.lock_path)
            except FileNotFoundError:
                pass
            return True

        result, ran = self._with_guard(_attempt, nonblocking=False)
        if ran and result:
            self._held = False
            return True
        return False

    def install_signal_handlers(self) -> None:
        def _handler(signum, frame):
            self.release()
            sys.exit(128 + signum)

        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                try:
                    signal.signal(sig, _handler)
                except (ValueError, OSError):
                    pass

    def __enter__(self):
        if not self.try_acquire():
            raise LockHeldByLiveProcess(self.label)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
