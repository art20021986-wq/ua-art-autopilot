#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import task049_gate_b_preflight as P  # noqa: E402


class FakeAPI:
    def __init__(self, tasks, source=b"source", candidate=b"candidate"):
        self.tasks = tasks
        self.source = source
        self.candidate = candidate

    def file(self, path):
        return self.source if path == P.SOURCE_PATH else self.candidate

    def always_on(self):
        return self.tasks


class PreflightTests(unittest.TestCase):
    def test_sanitized_task_never_relays_command(self):
        result = P.sanitize_task({
            "id": 7,
            "command": "python3.10 /home/Carix/start_safe.py",
            "enabled": True,
            "running": True,
        })
        self.assertNotIn("command", result)
        self.assertEqual(result["entrypoints"], ["start_safe.py"])
        self.assertEqual(len(result["command_sha256"]), 64)

    def test_inbox_trigger_is_not_production_candidate(self):
        source = b"source"
        candidate = b"candidate"
        with unittest.mock.patch.object(P, "EXPECTED_SOURCE_SHA", P.sha256(source)), \
             unittest.mock.patch.object(P, "EXPECTED_CANDIDATE_SHA", P.sha256(candidate)):
            receipt = P.run(FakeAPI([
                {"id": 1, "command": "python3.10 /home/Carix/start_safe.py", "enabled": True},
                {"id": 2, "command": "python3.10 /home/Carix/autopilot_inbox/start_safe.py", "enabled": True},
            ], source, candidate))
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual([item["id"] for item in receipt["production_candidates"]], [1])

    def test_multiple_production_tasks_block(self):
        source = b"source"
        candidate = b"candidate"
        with unittest.mock.patch.object(P, "EXPECTED_SOURCE_SHA", P.sha256(source)), \
             unittest.mock.patch.object(P, "EXPECTED_CANDIDATE_SHA", P.sha256(candidate)):
            receipt = P.run(FakeAPI([
                {"id": 1, "command": "python3.10 /home/Carix/start_safe.py", "enabled": True},
                {"id": 2, "command": "python3.10 /home/Carix/team_bot.py", "enabled": True},
            ], source, candidate))
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("production_task_count:2", receipt["errors"])

    def test_disabled_task_is_not_candidate(self):
        item = P.sanitize_task({
            "id": 3,
            "command": "python3.10 /home/Carix/team_bot.py",
            "enabled": False,
        })
        self.assertFalse(item["enabled"])

    def test_arbitrary_file_path_refused(self):
        api = P.ReadOnlyAPI(P.USERNAME, P.HOSTS[0], "x", opener=lambda *_a, **_k: None)
        with self.assertRaisesRegex(P.PreflightBlocked, "file_path_not_allowed"):
            api.file("/home/Carix/crm.db")


if __name__ == "__main__":
    unittest.main()

