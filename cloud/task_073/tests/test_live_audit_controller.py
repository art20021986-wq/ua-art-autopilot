import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import live_audit_controller as lac


class TestLiveAuditController(unittest.TestCase):
    def test_blocked_without_credentials(self):
        for var in lac.REQUIRED_ENV_VARS:
            os.environ.pop(var, None)
        result = lac.run_get_only_audit("/tmp/nonexistent_task073_audit_dir")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("MISSING_CREDENTIALS", result["reason"])


if __name__ == "__main__":
    unittest.main()
