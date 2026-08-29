"""STT circuit breaker.

After 3 STT hangs/timeouts within a rolling 10-minute window, opens a 5
minute cooldown during which voice/audio processing is short-circuited to
an immediate failure message (text/button input keeps working). Also used
as the restart-budget gate for the (conditional) full-process restart path.
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque

HANG_WINDOW_SECONDS = 10 * 60
HANG_THRESHOLD = 3
COOLDOWN_SECONDS = 5 * 60

PROCESS_RESTART_WINDOW_SECONDS = 10 * 60
PROCESS_RESTART_MAX = 2
PROCESS_RESTART_COOLDOWN_SECONDS = 10 * 60
HEALTH_PROBE_FAIL_STREAK_REQUIRED = 3


class STTCircuitBreaker:
    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = Lock()
        self._hangs: Deque[float] = deque()
        self._cooldown_until: float = 0.0

    def record_hang(self) -> None:
        now = self._clock()
        with self._lock:
            self._hangs.append(now)
            self._trim(now)
            if len(self._hangs) >= HANG_THRESHOLD:
                self._cooldown_until = now + COOLDOWN_SECONDS
                self._hangs.clear()

    def _trim(self, now: float) -> None:
        while self._hangs and now - self._hangs[0] > HANG_WINDOW_SECONDS:
            self._hangs.popleft()

    def is_open(self) -> bool:
        now = self._clock()
        with self._lock:
            return now < self._cooldown_until

    def cooldown_remaining(self) -> float:
        now = self._clock()
        with self._lock:
            return max(0.0, self._cooldown_until - now)


class ProcessRestartBudget:
    """Guards the (conditionally allowed) full-process restart path.

    Requires: 3 consecutive failed health probes, exit code 75, at most 2
    process restarts within a 10 minute window, then a cooldown.
    """

    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = Lock()
        self._fail_streak = 0
        self._restarts: Deque[float] = deque()
        self._cooldown_until = 0.0

    def record_health_probe(self, healthy: bool) -> None:
        with self._lock:
            if healthy:
                self._fail_streak = 0
            else:
                self._fail_streak += 1

    def probes_justify_restart(self) -> bool:
        with self._lock:
            return self._fail_streak >= HEALTH_PROBE_FAIL_STREAK_REQUIRED

    def may_restart(self) -> bool:
        now = self._clock()
        with self._lock:
            if now < self._cooldown_until:
                return False
            while self._restarts and now - self._restarts[0] > PROCESS_RESTART_WINDOW_SECONDS:
                self._restarts.popleft()
            return len(self._restarts) < PROCESS_RESTART_MAX

    def record_restart(self) -> None:
        now = self._clock()
        with self._lock:
            self._restarts.append(now)
            if len(self._restarts) >= PROCESS_RESTART_MAX:
                self._cooldown_until = now + PROCESS_RESTART_COOLDOWN_SECONDS
            self._fail_streak = 0

    EXIT_CODE_SUPERVISOR_RESTART = 75
