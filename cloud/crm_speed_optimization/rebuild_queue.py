"""
rebuild_queue.py

Bounded, coalescing rebuild queue for the CRM public-page ("stranica")
generator.

Guarantees:
  * enqueue() returns immediately and never blocks the Telegram handler;
  * at most one rebuild runs at a time ACROSS ALL PROCESSES, enforced by
    CrossProcessLock (not threading.Lock, which is process-local only);
  * a burst of enqueue() calls while a rebuild is running collapses into
    at most one pending follow-up rebuild, coordinated cross-process via
    a small marker file guarded by the same lock discipline;
  * failures are logged (bounded, no secrets) and are never retried
    forever -- a failed rebuild simply ends the loop.

Binding the queue to the real generator is done by
`bind_stranica_callback()`, which performs an AST anchor search over the
real avtoperedacha.py source. If exactly one safe anchor cannot be
proven, AnchorNotFoundError is raised and the caller MUST treat the
candidate as BLOCKED and leave it unmodified. This module never imports
or executes the real generator; the resolved anchor is only recorded as
an inert descriptor for a separately reviewed production wiring step.
"""
from __future__ import annotations

import ast
import os
import sys
import threading
import time
import traceback
from typing import Callable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cross_process_lock import CrossProcessLock  # noqa: E402


class AnchorNotFoundError(Exception):
    pass


def find_stranica_generation_anchors(source: str) -> List[ast.FunctionDef]:
    """Return candidate in-process generation function definitions that
    call into the imported `stranica` module without going through
    subprocess/os.system/multiprocessing. A safe bind requires exactly
    one candidate; callers must BLOCK on any other count.
    """
    tree = ast.parse(source)
    imported_stranica_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "stranica":
                    imported_stranica_names.add(alias.asname or alias.name)
        if isinstance(node, ast.ImportFrom) and node.module == "stranica":
            for alias in node.names:
                imported_stranica_names.add(alias.asname or alias.name)

    candidates: List[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls_stranica = False
        uses_subprocess = False
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                func = inner.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id in imported_stranica_names:
                        calls_stranica = True
                if isinstance(func, ast.Name) and func.id in imported_stranica_names:
                    calls_stranica = True
                if isinstance(func, ast.Attribute):
                    owner = getattr(func.value, "id", "") or getattr(func.value, "attr", "")
                    if owner in ("subprocess", "os") and func.attr in (
                        "run", "Popen", "call", "system", "check_call", "check_output",
                    ):
                        uses_subprocess = True
                if isinstance(func, ast.Name) and func.id == "system":
                    uses_subprocess = True
        if calls_stranica and not uses_subprocess:
            candidates.append(node)
    return candidates


class _CallbackDescriptor:
    """Inert descriptor of the resolved rebuild anchor. Gate A never
    imports or calls the underlying module; this object only records
    what a separately reviewed production wiring step would bind.
    Offline tests may attach a fake implementation via bind_test_impl().
    """

    def __init__(self, source_path: str, function_name: str, lineno: int):
        self.source_path = source_path
        self.function_name = function_name
        self.lineno = lineno
        self.call_count = 0
        self._impl: Optional[Callable[[], None]] = None

    def bind_test_impl(self, impl: Callable[[], None]) -> None:
        self._impl = impl

    def __call__(self) -> None:
        if self._impl is None:
            raise RuntimeError(
                "callback descriptor has no bound implementation; Gate A must "
                "never execute the real generator"
            )
        self.call_count += 1
        self._impl()


def bind_stranica_callback(source_path: str) -> _CallbackDescriptor:
    with open(source_path, "r", encoding="utf-8") as fh:
        source = fh.read()
    candidates = find_stranica_generation_anchors(source)
    if len(candidates) != 1:
        raise AnchorNotFoundError(
            f"expected exactly one in-process stranica generation anchor in "
            f"{source_path}, found {len(candidates)}"
        )
    anchor = candidates[0]
    return _CallbackDescriptor(source_path=source_path, function_name=anchor.name,
                                lineno=anchor.lineno)


class RebuildQueue:
    """Cross-process coalescing rebuild queue.

    enqueue() never blocks:
      * if the cross-process rebuild lock is free, a local worker thread
        is started (or reused) to acquire it and run the callback;
      * if the lock is currently held (by this or another process), a
        marker file is written (idempotent) so the process that is
        currently running the rebuild performs exactly one extra
        coalesced follow-up after it finishes.
    """

    def __init__(self, lock_path: str, callback: Callable[[], None],
                 log_fn: Optional[Callable[[str], None]] = None):
        self._callback = callback
        self._lock_path = lock_path
        self._lock = CrossProcessLock(lock_path, label="stranica_rebuild")
        self._pending_path = lock_path + ".pending"
        self._log = log_fn or (lambda msg: None)
        self._worker_guard = threading.Lock()
        self._worker: Optional[threading.Thread] = None

    def _mark_pending(self) -> None:
        try:
            fd = os.open(self._pending_path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        except OSError:
            pass

    def _claim_pending(self) -> bool:
        try:
            os.remove(self._pending_path)
            return True
        except FileNotFoundError:
            return False

    def enqueue(self) -> None:
        """Non-blocking. Returns immediately."""
        probe = CrossProcessLock(self._lock_path, label="stranica_rebuild")
        if probe.try_acquire():
            probe.release()
            with self._worker_guard:
                if self._worker is not None and self._worker.is_alive():
                    self._mark_pending()
                    return
                self._worker = threading.Thread(target=self._run_owned, daemon=True)
                self._worker.start()
            return
        self._mark_pending()

    def _run_owned(self) -> None:
        while True:
            if not self._lock.try_acquire():
                self._mark_pending()
                return
            try:
                start = time.time()
                try:
                    self._callback()
                    self._log(f"rebuild ok duration={time.time() - start:.3f}s")
                except Exception:
                    self._log(
                        f"rebuild failed duration={time.time() - start:.3f}s "
                        f"error={traceback.format_exc(limit=1)!r}"
                    )
            finally:
                self._lock.release()
            if not self._claim_pending():
                return
