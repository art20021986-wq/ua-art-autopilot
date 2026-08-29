#!/usr/bin/env python3
"""Killable, bounded STT worker controller for CRM-VOICE-WATCHDOG-005.

This release candidate is not wired to production.  The parent Telegram
process remains responsive because every STT call lives in a disposable child
process group that can be terminated on timeout.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import datetime as dt
import json
import math
import os
import pathlib
import signal
import sys
import tempfile
import weakref
from collections import deque
from typing import Awaitable, Callable, Optional


MIN_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 180
TIMEOUT_MULTIPLIER = 1.5
TIMEOUT_OVERHEAD_SECONDS = 10
MAX_ATTEMPTS = 2
TERM_GRACE_SECONDS = 3
RESTART_WINDOW_SECONDS = 600
MAX_RESTARTS_PER_WINDOW = 3
COOLDOWN_SECONDS = 300
MAX_CONCURRENT_WORKERS = 2


class VoiceWatchdogError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class AttemptResult:
    ok: bool
    text: str = ""
    error: str = ""
    timed_out: bool = False
    child_terminated: bool = False


@dataclasses.dataclass(frozen=True)
class VoiceResult:
    ok: bool
    text: str
    attempts: int
    restarted_workers: int
    error: str = ""
    retryable: bool = False


def timeout_for_duration(duration_seconds: object) -> int:
    try:
        duration = max(0.0, float(duration_seconds or 0))
    except (TypeError, ValueError):
        duration = 0.0
    proposed = math.ceil(duration * TIMEOUT_MULTIPLIER) + TIMEOUT_OVERHEAD_SECONDS
    return max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, proposed))


def download_timeout_for_duration(duration_seconds: object) -> int:
    try:
        duration = max(0.0, float(duration_seconds or 0))
    except (TypeError, ValueError):
        duration = 0.0
    return max(5, min(30, math.ceil(duration / 4.0) + 5))


class RestartBudget:
    """Bounded restart/cooldown state; serializable for a durable adapter."""

    def __init__(self) -> None:
        self._restarts: deque[float] = deque()
        self.cooldown_until = 0.0

    def allow(self, now: float) -> bool:
        while self._restarts and now - self._restarts[0] > RESTART_WINDOW_SECONDS:
            self._restarts.popleft()
        return now >= self.cooldown_until and len(self._restarts) < MAX_RESTARTS_PER_WINDOW

    def record(self, now: float) -> None:
        while self._restarts and now - self._restarts[0] > RESTART_WINDOW_SECONDS:
            self._restarts.popleft()
        self._restarts.append(now)
        if len(self._restarts) >= MAX_RESTARTS_PER_WINDOW:
            self.cooldown_until = now + COOLDOWN_SECONDS

    def snapshot(self) -> dict:
        return {"restarts": list(self._restarts), "cooldown_until": self.cooldown_until}


_GLOBAL_RESTART_BUDGET = RestartBudget()
_LOOP_LIMITS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _worker_limit_for_current_loop() -> asyncio.Semaphore:
    """Return one bounded STT semaphore per Telegram event loop."""
    loop = asyncio.get_running_loop()
    limit = _LOOP_LIMITS.get(loop)
    if limit is None:
        limit = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)
        _LOOP_LIMITS[loop] = limit
    return limit


async def _terminate_process_group(process: asyncio.subprocess.Process) -> bool:
    if process.returncode is not None:
        return True
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    try:
        await asyncio.wait_for(process.wait(), timeout=TERM_GRACE_SECONDS)
        return True
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        return True


async def run_killable_attempt(
    audio_bytes: bytes,
    filename: str,
    timeout_seconds: int,
    *,
    python_executable: str = sys.executable,
    worker_path: Optional[pathlib.Path] = None,
) -> AttemptResult:
    worker = pathlib.Path(worker_path or __file__).resolve()
    safe_filename = pathlib.PurePath(filename or "voice.ogg").name
    with tempfile.TemporaryDirectory(prefix="crm-voice-worker-") as directory:
        root = pathlib.Path(directory)
        input_path = root / "input.bin"
        output_path = root / "output.json"
        input_path.write_bytes(audio_bytes)
        process = await asyncio.create_subprocess_exec(
            python_executable,
            str(worker),
            "--worker",
            str(input_path),
            str(output_path),
            safe_filename,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            _stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            terminated = await _terminate_process_group(process)
            return AttemptResult(
                False,
                error="STT_TIMEOUT",
                timed_out=True,
                child_terminated=terminated,
            )
        except asyncio.CancelledError:
            await _terminate_process_group(process)
            raise
        if process.returncode != 0:
            detail = (stderr or b"").decode("utf-8", "replace")[-500:]
            return AttemptResult(False, error="STT_CHILD_FAILED:" + detail)
        try:
            value = json.loads(output_path.read_text(encoding="utf-8"))
            text = str(value.get("text") or "").strip()
        except Exception as exc:
            return AttemptResult(False, error="STT_OUTPUT_INVALID:" + type(exc).__name__)
        return AttemptResult(bool(text), text=text, error="" if text else "STT_EMPTY")


async def transcribe_with_restart(
    audio_bytes: bytes,
    filename: str,
    duration_seconds: object,
    *,
    run_attempt: Callable[[bytes, str, int], Awaitable[AttemptResult]] = run_killable_attempt,
    budget: Optional[RestartBudget] = None,
    clock: Callable[[], float] | None = None,
    worker_limit: Optional[asyncio.Semaphore] = None,
) -> VoiceResult:
    loop = asyncio.get_running_loop()
    now_fn = clock or loop.time
    budget = budget or _GLOBAL_RESTART_BUDGET
    worker_limit = worker_limit or _worker_limit_for_current_loop()
    timeout = timeout_for_duration(duration_seconds)
    last_error = "STT_FAILED"
    restarted = 0
    for attempt_number in range(1, MAX_ATTEMPTS + 1):
        async with worker_limit:
            result = await run_attempt(audio_bytes, filename, timeout)
        if result.ok and result.text.strip():
            return VoiceResult(True, result.text.strip(), attempt_number, restarted)
        last_error = result.error or "STT_FAILED"
        if attempt_number >= MAX_ATTEMPTS:
            break
        now = now_fn()
        if not budget.allow(now):
            return VoiceResult(
                False,
                "",
                attempt_number,
                restarted,
                error="STT_COOLDOWN",
                retryable=True,
            )
        budget.record(now)
        restarted += 1
    return VoiceResult(
        False,
        "",
        MAX_ATTEMPTS,
        restarted,
        error=last_error,
        retryable=True,
    )


def _worker(input_path: str, output_path: str, filename: str) -> int:
    """Child-only entrypoint.  It cannot mutate CRM state."""
    import ai  # imported only inside the disposable worker

    audio = pathlib.Path(input_path).read_bytes()
    text = str(ai.transcribe(audio, pathlib.PurePath(filename).name) or "").strip()
    target = pathlib.Path(output_path)
    temporary = target.with_name("." + target.name + ".tmp")
    temporary.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, target)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("input_path", nargs="?")
    parser.add_argument("output_path", nargs="?")
    parser.add_argument("filename", nargs="?")
    args = parser.parse_args(argv)
    if not args.worker or not all((args.input_path, args.output_path, args.filename)):
        raise SystemExit("WORKER_ARGUMENTS_REQUIRED")
    return _worker(args.input_path, args.output_path, args.filename)


if __name__ == "__main__":
    raise SystemExit(main())
