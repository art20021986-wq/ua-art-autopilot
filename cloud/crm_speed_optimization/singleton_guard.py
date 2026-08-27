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
