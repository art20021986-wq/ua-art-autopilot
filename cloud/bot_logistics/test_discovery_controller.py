#!/usr/bin/env python3
"""Offline, standard-library-only tests for pythonanywhere_discovery_controller.py.

A FakeTransport simulates the PythonAnywhere surface. No network call is ever
made. These tests prove PASS relay, BLOCKED relay, stale/tampered/malformed
rejection, forbidden-endpoint blocking, and guaranteed cleanup.
"""
import json
import os
import shutil
import tempfile
import time
import unittest

import pythonanywhere_discovery_controller as ctrl


class FakeTransport(object):
    def __init__(self):
        self.files = {}
        self.always_on_created = False
        self.always_on_deleted = False
        self.scheduled_created = False
        self.scheduled_deleted = False
        self.deleted_files = []

    def read_file(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def create_always_on_task(self, command, output_redirect):
        self.last_command = command
        self.last_output_redirect = output_redirect
        self.always_on_created = True

    def delete_always_on_task(self):
        self.always_on_deleted = True

    def create_scheduled_task_fallback(self, command, output_redirect):
        self.scheduled_created = True

    def delete_scheduled_task_fallback(self):
        self.scheduled_deleted = True

    def delete_file(self, path):
        self.deleted_files.append(path)
        self.files.pop(path, None)


def _manifest(sha, status="PASS", executed=False, prod=False, age=0):
    return json.dumps({
        "status": status,
        "executed_remote_code": executed,
        "production_touched": prod,
        "discovery_script_sha256": sha,
        "generated_at_epoch": time.time() - age,
    })


def _receipt(status="PASS", container_status="ALREADY_CORRECT"):
    r = {
        "task_id": "task_037",
        "mode": "READ_ONLY_DISCOVERY",
        "status": status,
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "ua0009_published": False,
        "sources": [],
        "db": {},
        "errors": [],
    }
    if status == "PASS":
        r["UA0006_CONTAINER_STATUS"] = container_status
    else:
        r["errors"] = ["ua0006_no_match_found"]
    return json.dumps(r, sort_keys=True)


class ControllerTestBase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ctrl_test_")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

        orig_evidence = ctrl.EVIDENCE_PATH_LOCAL
        orig_report = ctrl.REPORT_PATH_LOCAL
        ctrl.EVIDENCE_PATH_LOCAL = os.path.join(self.tmpdir, "evidence", "task_037_discovery.json")
        ctrl.REPORT_PATH_LOCAL = os.path.join(self.tmpdir, "TASK_039_DISCOVERY_CONTROLLER_REPORT.md")
        self.addCleanup(setattr, ctrl, "EVIDENCE_PATH_LOCAL", orig_evidence)
        self.addCleanup(setattr, ctrl, "REPORT_PATH_LOCAL", orig_report)

        self.transport = FakeTransport()
        self.env = {
            "PYTHONANYWHERE_USERNAME": "Carix",
            "PYTHONANYWHERE_HOST": "www.pythonanywhere.com",
            "PYTHONANYWHERE_API_TOKEN": "fake-token-not-real",
        }

        def fake_subprocess_runner(cmd):
            return 0, "", ""

        self.controller = ctrl.DiscoveryController(
            transport=self.transport, env=self.env,
            sleep=lambda s: None, subprocess_runner=fake_subprocess_runner,
            timeout=5, poll_interval=0.01,
        )

    def _seed_manifest(self, **kwargs):
        sha = ctrl.sha256_file(ctrl.DISCOVERY_SCRIPT_LOCAL)
        self.transport.files[ctrl.REMOTE_MANIFEST_PATH] = _manifest(sha, **kwargs)
        return sha


class TestPassAndBlockedRelay(ControllerTestBase):
    def test_pass_relay(self):
        self._seed_manifest()
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = _receipt("PASS")
        result = self.controller.run()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(os.path.exists(ctrl.EVIDENCE_PATH_LOCAL))
        self.assertTrue(os.path.exists(ctrl.REPORT_PATH_LOCAL))

    def test_blocked_relay_not_upgraded(self):
        self._seed_manifest()
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = _receipt("BLOCKED")
        result = self.controller.run()
        self.assertEqual(result["status"], "BLOCKED")

    def test_cleanup_always_happens_on_success(self):
        self._seed_manifest()
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = _receipt("PASS")
        self.controller.run()
        self.assertTrue(self.transport.always_on_deleted)
        self.assertIn(ctrl.REMOTE_OUTPUT_PATH, self.transport.deleted_files)

    def test_cleanup_always_happens_on_failure(self):
        self._seed_manifest()
        # no output ever appears -> timeout
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()
        self.assertTrue(self.transport.always_on_deleted)


class TestRejectionPaths(ControllerTestBase):
    def test_stale_receipt_rejected(self):
        self._seed_manifest(age=ctrl.MAX_RECEIPT_AGE_SECONDS + 100)
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_wrong_sha_rejected(self):
        self.transport.files[ctrl.REMOTE_MANIFEST_PATH] = _manifest("deadbeef" * 8)
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_malformed_json_rejected(self):
        self._seed_manifest()
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = "{not json"
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_duplicate_keys_rejected(self):
        self._seed_manifest()
        raw = '{"task_id": "task_037", "task_id": "task_037"}'
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = raw
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_secret_shaped_output_rejected(self):
        self._seed_manifest()
        r = json.loads(_receipt("PASS"))
        r["errors"] = ["api_key=should_not_appear_here"]
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = json.dumps(r)
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_wrong_username_rejected(self):
        self.env["PYTHONANYWHERE_USERNAME"] = "someone_else"
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_wrong_host_rejected(self):
        self.env["PYTHONANYWHERE_HOST"] = "evil.example.com"
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_missing_token_rejected(self):
        del self.env["PYTHONANYWHERE_API_TOKEN"]
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_timeout_rejected(self):
        self._seed_manifest()
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_manifest_production_touched_true_rejected(self):
        sha = ctrl.sha256_file(ctrl.DISCOVERY_SCRIPT_LOCAL)
        self.transport.files[ctrl.REMOTE_MANIFEST_PATH] = _manifest(sha, prod=True)
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_manifest_executed_remote_code_true_rejected(self):
        sha = ctrl.sha256_file(ctrl.DISCOVERY_SCRIPT_LOCAL)
        self.transport.files[ctrl.REMOTE_MANIFEST_PATH] = _manifest(sha, executed=True)
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_receipt_unsafe_field_rejected(self):
        self._seed_manifest()
        r = json.loads(_receipt("PASS"))
        r["production_write"] = True
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = json.dumps(r)
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()


class TestCommandAndPathExactness(ControllerTestBase):
    def test_exact_remote_command(self):
        self._seed_manifest()
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = _receipt("PASS")
        self.controller.run()
        self.assertEqual(self.transport.last_command, ctrl.EXACT_COMMAND)
        self.assertIn("python3.10", ctrl.EXACT_COMMAND)
        self.assertIn(ctrl.REMOTE_DB_PATH, ctrl.EXACT_COMMAND)
        for s in ctrl.REMOTE_SOURCES:
            self.assertIn(s, ctrl.EXACT_COMMAND)

    def test_exact_output_path(self):
        self._seed_manifest()
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = _receipt("PASS")
        self.controller.run()
        self.assertEqual(self.transport.last_output_redirect, ctrl.REMOTE_OUTPUT_PATH)


class TestForbiddenEndpoints(ControllerTestBase):
    def test_forbidden_method_blocked(self):
        with self.assertRaises(ctrl.ControllerError):
            self.controller.api.write_file("/home/Carix/anything", b"data")

    def test_no_forbidden_calls_during_normal_run(self):
        self._seed_manifest()
        self.transport.files[ctrl.REMOTE_OUTPUT_PATH] = _receipt("PASS")
        self.controller.run()
        called_names = {name for name, _, _ in self.controller.api.calls}
        self.assertTrue(called_names.isdisjoint(set(ctrl.FORBIDDEN_API_METHODS)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
