#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import pathlib
import sys
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import voice_watchdog as v  # noqa: E402


class TimeoutPolicyTests(unittest.TestCase):
    def test_duration_scaled_and_bounded(self):
        expected = {0: 15, 3: 15, 30: 55, 60: 100, 120: 180, 600: 180}
        for duration, timeout in expected.items():
            self.assertEqual(v.timeout_for_duration(duration), timeout)

    def test_download_timeout_is_bounded(self):
        self.assertEqual(v.download_timeout_for_duration(0), 5)
        self.assertEqual(v.download_timeout_for_duration(600), 30)

    def test_restart_budget_enters_cooldown(self):
        budget = v.RestartBudget()
        for now in (0.0, 1.0, 2.0):
            self.assertTrue(budget.allow(now))
            budget.record(now)
        self.assertFalse(budget.allow(3.0))
        self.assertFalse(budget.allow(303.0))
        self.assertTrue(budget.allow(603.0))


class VoiceControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_voice_succeeds_once(self):
        calls = []

        async def runner(data, filename, timeout):
            calls.append((data, filename, timeout))
            return v.AttemptResult(True, text="готово")

        result = await v.transcribe_with_restart(b"a", "voice.ogg", 3, run_attempt=runner)
        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.restarted_workers, 0)
        self.assertEqual(len(calls), 1)

    async def test_hung_first_worker_is_restarted_once(self):
        results = [
            v.AttemptResult(False, error="STT_TIMEOUT", timed_out=True, child_terminated=True),
            v.AttemptResult(True, text="вторая попытка"),
        ]

        async def runner(_data, _filename, _timeout):
            return results.pop(0)

        result = await v.transcribe_with_restart(b"a", "voice.ogg", 60, run_attempt=runner)
        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.restarted_workers, 1)
        self.assertEqual(result.text, "вторая попытка")

    async def test_two_hangs_return_one_retryable_failure(self):
        calls = 0

        async def runner(_data, _filename, _timeout):
            nonlocal calls
            calls += 1
            return v.AttemptResult(
                False, error="STT_TIMEOUT", timed_out=True, child_terminated=True
            )

        result = await v.transcribe_with_restart(b"a", "voice.ogg", 120, run_attempt=runner)
        self.assertFalse(result.ok)
        self.assertTrue(result.retryable)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.restarted_workers, 1)
        self.assertEqual(calls, 2)

    async def test_cooldown_prevents_restart_loop(self):
        budget = v.RestartBudget()
        for now in (0.0, 1.0, 2.0):
            budget.record(now)

        async def runner(_data, _filename, _timeout):
            return v.AttemptResult(False, error="STT_TIMEOUT", timed_out=True)

        result = await v.transcribe_with_restart(
            b"a", "voice.ogg", 30, run_attempt=runner, budget=budget, clock=lambda: 3.0
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "STT_COOLDOWN")
        self.assertEqual(result.attempts, 1)


if __name__ == "__main__":
    unittest.main()
