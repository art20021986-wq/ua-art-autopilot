"""TASK_070 candidate: trace_zhurnal.py — OBSERVER ONLY.

Root cause fixed in this candidate:
  The original trace_zhurnal.py silently escalated SQLite timeout/busy_timeout
  to 30s inside _ua_connect and _Obertka.__enter__, which meant any caller
  requesting a short timeout was overridden and forced to wait up to 30s on
  a locked database. This candidate removes ALL connection/transaction
  mutation from trace_zhurnal. It only observes (logs) and never changes:
    - sqlite3 connect timeout
    - PRAGMA busy_timeout
    - PRAGMA journal_mode
    - transaction boundaries (BEGIN/COMMIT/ROLLBACK)
    - the return value / side effects of the wrapped call

This file is an ISOLATED CANDIDATE. It does not touch the production
trace_zhurnal.py. It is provided for Gate A review, testing, and future
controlled rollout only.
"""
from __future__ import annotations

import logging
import time
from contextlib import ContextDecorator
from typing import Any, Callable, Optional

log = logging.getLogger("trace_zhurnal_070")


def _ua_connect(*args: Any, **kwargs: Any):
    """OBSERVER-ONLY passthrough connect factory.

    CONTRACT: This function MUST NOT set or override 'timeout',
    'isolation_level', or issue any PRAGMA. The caller is fully
    responsible for the connection's timeout/pragma configuration.
    Any 'timeout' kwarg supplied by the caller is passed through
    UNCHANGED. If the caller does not pass timeout, we do not inject one.
    """
    import sqlite3

    conn = sqlite3.connect(*args, **kwargs)
    log.debug("trace_zhurnal_070: connection observed (no timeout/pragma mutation)")
    return conn


class _Obertka(ContextDecorator):
    """OBSERVER-ONLY wrapper.

    Previous (defective) behaviour: __enter__ raised any smaller timeout
    up to 30 seconds, defeating fast-fail writer contracts.

    New behaviour: __enter__/__exit__ ONLY measure duration and log the
    outcome (success / OperationalError / other exception). They never
    read, set, or mutate timeout, busy_timeout, journal_mode, or the
    transaction state of the wrapped connection/cursor. They never
    suppress or alter exceptions raised by the wrapped operation
    (in particular sqlite3.OperationalError must propagate unchanged
    so the writer contract can react to lock/busy conditions).
    """

    def __init__(self, label: str = "op", conn: Optional[Any] = None):
        self.label = label
        self.conn = conn  # kept for logging identity only, never mutated
        self._t0: float = 0.0

    def __enter__(self):
        self._t0 = time.monotonic()
        # NO timeout/busy_timeout/pragma mutation here. Observer only.
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.monotonic() - self._t0
        if exc_type is None:
            log.debug("trace_zhurnal_070: %s ok in %.3fs", self.label, dt)
        else:
            log.warning("trace_zhurnal_070: %s failed in %.3fs: %s", self.label, dt, exc)
        # Return False (or None) => never swallow exceptions.
        return False


def zhurnal(label: str = "op") -> Callable[[Callable], Callable]:
    """Decorator form kept for backward-compatible call sites.
    Purely observes timing; does not alter DB behaviour in any way.
    """

    def _decorator(fn: Callable) -> Callable:
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            with _Obertka(label=label):
                return fn(*args, **kwargs)

        return _wrapped

    return _decorator
