"""
singleton_guard.py

Thin compatibility wrapper delegating to the canonical CrossProcessLock /
SingletonGuard implementation in canonical_modules.py. This module carries
no divergent lock logic. A duplicate start exits quickly with a defined
nonzero diagnostic code and never disturbs another process's lock.
"""
from __future__ import annotations

import sys

from canonical_modules import CrossProcessLock, SingletonGuard

DUPLICATE_START_EXIT_CODE = 78

__all__ = [
    "CrossProcessLock",
    "SingletonGuard",
    "acquire_singleton_or_exit",
    "DUPLICATE_START_EXIT_CODE",
]


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
