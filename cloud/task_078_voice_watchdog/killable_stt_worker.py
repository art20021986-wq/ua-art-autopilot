"""Killable STT worker.

Replaces the unkillable `asyncio.to_thread(ai.transcribe, ...)` call with a
spawned child process that can be forcefully terminated (TERM then KILL)
without leaving orphan work behind. Designed to be imported by
handler_patch.py / the real cars_ui.py voice handler after Gate A + Gate B
approval.

Contract covered here (task_078):
- timeout computed by caller via compute_stt_timeout()/compute_download_timeout()
- STT runs in its own killable process (not an unkillable thread)
- on timeout: SIGTERM, wait up to 3s, then SIGKILL
- max 2 attempts total per message (1 automatic restart)
- zero orphan workers after the call returns
"""
from __future__ import annotations

import math
import multiprocessing as mp
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

DOWNLOAD_TIMEOUT_MIN = 5
DOWNLOAD_TIMEOUT_MAX = 30
STT_TIMEOUT_MIN = 15
STT_TIMEOUT_MAX = 180
STT_TIMEOUT_FIXED_ADD = 10
STT_TIMEOUT_DURATION_MULT = 1.5
TERM_GRACE_SECONDS = 3
MAX_ATTEMPTS = 2


def compute_stt_timeout(duration_seconds: Optional[float]) -> int:
    """clamp(15, ceil(duration*1.5)+10, 180)"""
    d = duration_seconds or 0
    if d < 0:
        d = 0
    raw = math.ceil(d * STT_TIMEOUT_DURATION_MULT) + STT_TIMEOUT_FIXED_ADD
    return max(STT_TIMEOUT_MIN, min(STT_TIMEOUT_MAX, raw))


def compute_download_timeout(hint_seconds: Optional[float] = None) -> int:
    """Bounded download timeout, independent of STT timeout."""
    h = hint_seconds or DOWNLOAD_TIMEOUT_MIN
    return max(DOWNLOAD_TIMEOUT_MIN, min(DOWNLOAD_TIMEOUT_MAX, int(math.ceil(h))))


def _child_entry(target: Callable[..., Any], args: tuple, kwargs: dict, q: "mp.Queue") -> None:
    try:
        result = target(*args, **kwargs)
        q.put(("ok", result))
    except Exception as exc:  # noqa: BLE001 - must report any child failure
        q.put(("error", repr(exc)))


@dataclass
class WorkerOutcome:
    status: str  # "ok" | "error" | "timeout"
    payload: Any
    killed: bool
    attempts: int


class KillableSTTWorker:
    """Runs `target(*args, **kwargs)` in a spawned, killable process."""

    def __init__(self, target: Callable[..., Any], mp_context: str = "spawn"):
        self._target = target
        self._ctx = mp.get_context(mp_context)

    def _run_once(self, timeout: float, args: tuple, kwargs: dict) -> Tuple[str, Any, bool]:
        q = self._ctx.Queue()
        proc = self._ctx.Process(target=_child_entry, args=(self._target, args, kwargs, q))
        proc.start()
        proc.join(timeout)
        killed = False
        if proc.is_alive():
            killed = True
            proc.terminate()  # SIGTERM
            proc.join(TERM_GRACE_SECONDS)
            if proc.is_alive():
                proc.kill()  # SIGKILL
                proc.join(1)
            # Drain queue defensively; timeout result wins regardless.
            try:
                while not q.empty():
                    q.get_nowait()
            except Exception:
                pass
            q.close()
            return "timeout", None, killed
        status, payload = ("error", "no_result")
        if not q.empty():
            status, payload = q.get()
        q.close()
        return status, payload, killed

    def run_with_single_restart(
        self, timeout: float, args: tuple = (), kwargs: Optional[dict] = None
    ) -> WorkerOutcome:
        """Runs up to MAX_ATTEMPTS (2) fresh worker attempts total."""
        kwargs = kwargs or {}
        attempts = 0
        last_killed = False
        for attempts in range(1, MAX_ATTEMPTS + 1):
            status, payload, killed = self._run_once(timeout, args, kwargs)
            last_killed = killed
            if status == "ok":
                return WorkerOutcome("ok", payload, last_killed, attempts)
            # timeout or error -> retry once with a fresh process, then stop
        return WorkerOutcome(status, payload, last_killed, attempts)
