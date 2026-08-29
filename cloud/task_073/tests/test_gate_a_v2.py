"""Offline unit tests for cloud/task_073/tools/gate_a_v2.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import gate_a_v2  # noqa: E402
from test_patcher_v2 import KONTEYNER_FIXTURE, CARS_UI_FIXTURE, STRANICA_FIXTURE  # noqa: E402


class TestGateANoCredentials(unittest.TestCase):
    def test_blocked_without_credentials(self):
        os.environ.pop("PYTHONANYWHERE_API_TOKEN", None)
        os.environ.pop("PYTHONANYWHERE_USERNAME", None)
        result = gate_a_v2.run()
        self.assertFalse(result.live_credentials_present)
        self.assertEqual(result.mode, "BLOCKED_NO_CREDENTIALS")
        self.assertFalse(result.passed)


class TestOfflineSelftest(unittest.TestCase):
    def test_offline_matrix_passes(self):
        fixtures = {
            "konteyner.py": KONTEYNER_FIXTURE,
            "cars_ui.py": CARS_UI_FIXTURE,
            "stranica.py": STRANICA_FIXTURE,
        }
        result = gate_a_v2.run_offline_selftest(fixtures)
        self.assertTrue(result.passed, msg=str(result.notes))
        self.assertEqual(result.mode, "OFFLINE_SELFTEST")
        self.assertIn("INNER_ACTIONS_IDEMPOTENT", result.checks)
        self.assertIn("OUTER_DUPLICATES_ZERO", result.checks)
        self.assertIn("TOGGLE_PUBLISH_ROLLBACK_PRESENT", result.checks)
        self.assertIn("SEO068_STALE_PRECONDITION_REMOVED", result.checks)


if __name__ == "__main__":
    unittest.main()
