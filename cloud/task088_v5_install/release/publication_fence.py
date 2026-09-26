"""Cooperative publication fence for filesystem-mutating CRM helpers.

This module is an isolated release candidate.  Importing it registers fork
cleanup but does not open the lock or mutate production files.  Production
integration must bind the exact reviewed source hashes
and call the fence *inside* the synchronous worker that performs a mutation.
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import stat
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_LOCK_PATH = Path("/home/Carix/.ua_art_publish_transaction.lock")


def _require_crm_activation() -> None:
    # Only an explicitly registered, unconfigured CRM is held. Importing the
    # fence in the separately authorised installer never manufactures a bot
    # binding or changes that process's existing canonical admission rules.
    runtime = sys.modules.get("uaart_price_sync_runtime")
    check = getattr(runtime, "require_crm_publication_ready", None)
    if callable(check):
        check()


class FenceError(RuntimeError):
    """Base class for fail-closed fence errors."""


class FenceTimeout(FenceError):
    """The existing publication fence did not become available in time."""


class FencePathError(FenceError):
    """The lock path was not an exact, safe regular file."""


@dataclass
class _State:
    owner_thread: int | None = None
    depth: int = 0
    fd: int | None = None
    acquiring_thread: int | None = None


_condition = threading.Condition(threading.RLock())
_states: dict[str, _State] = {}
_registry_pid = os.getpid()


def _reset_after_fork_if_needed() -> None:
    global _condition, _registry_pid
    pid = os.getpid()
    if pid != _registry_pid:
        # File descriptors inherited across fork must never be treated as a
        # valid child-side reentrant lease or keep the parent's lease alive.
        for state in _states.values():
            if state.fd is not None:
                with contextlib.suppress(OSError):
                    os.close(state.fd)
        _states.clear()
        _registry_pid = pid
        # The inherited condition may be owned by a thread absent in the
        # child.  Recreate it before any child-side attempt to acquire it.
        _condition = threading.Condition(threading.RLock())


def _before_fork() -> None:
    # Opening/registering and closing/unregistering descriptors occur under
    # this condition, so the child inherits a complete descriptor registry.
    _condition.acquire()


def _after_fork_parent() -> None:
    _condition.release()


def _after_fork_child() -> None:
    # Only close descriptors: LOCK_UN would also revoke the parent's lease
    # because flock state belongs to the inherited open-file description.
    _reset_after_fork_if_needed()


os.register_at_fork(
    before=_before_fork,
    after_in_parent=_after_fork_parent,
    after_in_child=_after_fork_child,
)


def _validate_parent(path: Path) -> None:
    if not path.is_absolute():
        raise FencePathError("PUBLICATION_FENCE_ABSOLUTE_PATH_REQUIRED")
    try:
        if path.parent.resolve(strict=True) != path.parent:
            raise FencePathError("PUBLICATION_FENCE_CANONICAL_PARENT_REQUIRED")
    except OSError as exc:
        raise FencePathError("PUBLICATION_FENCE_PARENT_REQUIRED") from exc


def _validate_lock_file(path: Path, fd: int) -> None:
    _validate_parent(path)
    try:
        opened = os.fstat(fd)
        linked = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise FencePathError("PUBLICATION_FENCE_PATH_CHANGED") from exc
    if not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(linked.st_mode):
        raise FencePathError("PUBLICATION_FENCE_REGULAR_FILE_REQUIRED")
    if (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino):
        raise FencePathError("PUBLICATION_FENCE_PATH_CHANGED")


def _safe_open(path: Path) -> int:
    _validate_parent(path)
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise FencePathError("PUBLICATION_FENCE_UNSAFE_PATH") from exc
        raise
    try:
        _validate_lock_file(path, fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _lock_fd(fd: int, deadline: float, poll_interval: float) -> None:
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FenceTimeout("PUBLICATION_FENCE_TIMEOUT") from exc
            time.sleep(min(poll_interval, remaining))


class PublicationFence:
    """Same-thread reentrant, cross-thread and cross-process exclusive fence.

    Lock ordering is deliberately one-way: acquire this publication fence
    before opening a SQLite write transaction.  This class never acquires a
    database or spec lock and therefore cannot silently invert that order.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        poll_interval: float = 0.05,
        lock_path: Path | str = DEFAULT_LOCK_PATH,
        _test_only_path: bool = False,
    ) -> None:
        path = Path(lock_path)
        if path != DEFAULT_LOCK_PATH and not _test_only_path:
            raise FencePathError("EXACT_PRODUCTION_FENCE_PATH_REQUIRED")
        if timeout < 0 or poll_interval <= 0:
            raise ValueError("NONNEGATIVE_TIMEOUT_AND_POSITIVE_POLL_REQUIRED")
        self.path = path
        self.timeout = float(timeout)
        self.poll_interval = float(poll_interval)
        self._entered = False

    def __enter__(self) -> "PublicationFence":
        _require_crm_activation()
        _reset_after_fork_if_needed()
        if self._entered:
            raise FenceError("FENCE_INSTANCE_ALREADY_ENTERED")
        deadline = time.monotonic() + self.timeout
        thread_id = threading.get_ident()
        key = os.fspath(self.path)

        with _condition:
            state = _states.setdefault(key, _State())
            if state.owner_thread == thread_id:
                if state.fd is None:
                    raise FenceError("PUBLICATION_FENCE_DESCRIPTOR_MISSING")
                _validate_lock_file(self.path, state.fd)
                state.depth += 1
                self._entered = True
                return self
            while state.owner_thread is not None or state.acquiring_thread is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FenceTimeout("PUBLICATION_FENCE_TIMEOUT")
                _condition.wait(remaining)
            state.acquiring_thread = thread_id

        fd: int | None = None
        try:
            with _condition:
                fd = _safe_open(self.path)
                state.fd = fd
            _lock_fd(fd, deadline, self.poll_interval)
            with _condition:
                state = _states[key]
                if state.acquiring_thread != thread_id or state.owner_thread is not None:
                    raise FenceError("PUBLICATION_FENCE_REGISTRY_DRIFT")
                # Opening may precede a long flock wait.  Refuse a stale
                # inode if the lock path changed before granting the lease.
                _validate_lock_file(self.path, fd)
                state.acquiring_thread = None
                state.owner_thread = thread_id
                state.depth = 1
                state.fd = fd
                self._entered = True
            return self
        except BaseException:
            with _condition:
                state = _states.get(key)
                try:
                    if fd is not None:
                        with contextlib.suppress(OSError):
                            fcntl.flock(fd, fcntl.LOCK_UN)
                        os.close(fd)
                finally:
                    if state is not None and state.acquiring_thread == thread_id:
                        state.fd = None
                        state.acquiring_thread = None
                        _condition.notify_all()
            raise

    def __exit__(self, exc_type, exc, traceback) -> bool:
        _reset_after_fork_if_needed()
        if not self._entered:
            raise FenceError("FENCE_INSTANCE_NOT_ENTERED")
        key = os.fspath(self.path)
        thread_id = threading.get_ident()
        fd: int | None = None
        with _condition:
            state = _states.get(key)
            if state is None or state.owner_thread != thread_id or state.depth <= 0:
                raise FenceError("PUBLICATION_FENCE_NOT_OWNED_BY_THREAD")
            state.depth -= 1
            self._entered = False
            if state.depth:
                return False
            fd = state.fd
            try:
                if fd is None:
                    raise FenceError("PUBLICATION_FENCE_DESCRIPTOR_MISSING")
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                try:
                    if fd is not None:
                        os.close(fd)
                finally:
                    state.fd = None
                    state.owner_thread = None
                    _condition.notify_all()
        return False


def publication_fence(*, timeout: float = 30.0) -> PublicationFence:
    return PublicationFence(timeout=timeout)


def require_publication_fence(*, lock_path: Path | str = DEFAULT_LOCK_PATH) -> None:
    """Fail unless the current thread owns the cooperative fence."""
    _require_crm_activation()
    _reset_after_fork_if_needed()
    key = os.fspath(Path(lock_path))
    with _condition:
        state = _states.get(key)
        if state is None or state.owner_thread != threading.get_ident() or state.depth <= 0:
            raise FenceError("PUBLICATION_FENCE_REQUIRED")
        if state.fd is None:
            raise FenceError("PUBLICATION_FENCE_DESCRIPTOR_MISSING")
        _validate_lock_file(Path(lock_path), state.fd)
