"""Offline unit tests for cloud/task_073/tools/gate_b_controller_v2.py."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import gate_b_installer_v2 as installer_mod  # noqa: E402
import gate_b_controller_v2 as controller_mod  # noqa: E402
import postcheck_v2 as postcheck  # noqa: E402


class TestGateBController(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="task073_gbc_")
        self.target = os.path.join(self.tmpdir, "katalog.html")
        with open(self.target, "w", encoding="utf-8") as fh:
            fh.write("<html>old</html>")
        self.sha = installer_mod.sha256_file(self.target)
        self.write_set = [
            installer_mod.WriteSetEntry(
                target_path=self.target,
                new_content=b"<html>new-with-UA-0011</html>",
                preimage_sha=self.sha,
            )
        ]
        self._orig_verify = postcheck.immediate_and_delayed_verify

    def tearDown(self):
        postcheck.immediate_and_delayed_verify = self._orig_verify

    def _make_controller(self, verify_ok=True):
        def ok_true():
            return True

        def fake_verify(base_url, auto_number, revision_marker, delay_seconds=60.0, sleep_fn=None, fetcher=None):
            result = postcheck.VerifyResult(url="x", ok=verify_ok,
                                             reason="ok" if verify_ok else "fail",
                                             final_url="x", status=200)
            return {"immediate": result, "diagnostics": result, "delayed": result, "ok": verify_ok}

        postcheck.immediate_and_delayed_verify = fake_verify

        return controller_mod.GateBController(
            write_set=self.write_set,
            base_url="https://uaartlogistics.com",
            auto_number="UA-0011",
            revision_marker="rev1",
            preflight_fn=ok_true,
            dry_run_fn=ok_true,
            reload_fn=ok_true,
            exclusive_window_fn=ok_true,
        )

    def test_rejects_wrong_approval_token(self):
        controller = self._make_controller()
        with self.assertRaises(controller_mod.ApprovalError):
            controller.run("wrong-token")
        with open(self.target, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "<html>old</html>")

    def test_full_pass_with_exact_token(self):
        controller = self._make_controller(verify_ok=True)
        report = controller.run(controller_mod.REQUIRED_APPROVAL_TOKEN, delay_seconds=0, sleep_fn=lambda s: None)
        self.assertEqual(report.final_status, "PASS")
        with open(self.target, "r", encoding="utf-8") as fh:
            self.assertIn("UA-0011", fh.read())

    def test_rollback_on_verify_failure(self):
        controller = self._make_controller(verify_ok=False)
        with self.assertRaises(controller_mod.GateBFailure):
            controller.run(controller_mod.REQUIRED_APPROVAL_TOKEN, delay_seconds=0, sleep_fn=lambda s: None)
        self.assertTrue(controller.report.rollback_performed)
        with open(self.target, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "<html>old</html>")


if __name__ == "__main__":
    unittest.main()
