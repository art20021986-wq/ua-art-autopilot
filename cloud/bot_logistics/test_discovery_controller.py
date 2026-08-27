#!/usr/bin/env python3
"""Offline tests for the real TASK 039 PythonAnywhere controller."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

THIS_DIR = pathlib.Path(__file__).resolve().parent
CLOUD_DIR = THIS_DIR.parent
if str(CLOUD_DIR) not in sys.path:
    sys.path.insert(0, str(CLOUD_DIR))

from bot_logistics import pythonanywhere_discovery_controller as ctrl  # noqa: E402

NOW = dt.datetime(2026, 8, 27, 20, 0, tzinfo=dt.timezone.utc)


class FakeAPI:
    def __init__(self, events):
        self.events = events
        self.files = {}
        self.next_output = None
        self.always_available = True
        self.schedule_available = True
        self.deleted_outputs = []
        self.deleted_triggers = []
        self.commands = []

    def read_file(self, path):
        self.events.append(("api", "read_file", path))
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def delete_output(self, path):
        self.events.append(("api", "delete_output", path))
        self.deleted_outputs.append(path)
        self.files.pop(path, None)

    def _publish(self):
        if self.next_output is not None:
            self.files[ctrl.REMOTE_OUTPUT_PATH] = self.next_output

    def create_always_on_task(self, command):
        self.events.append(("api", "create_always_on", command))
        self.commands.append(command)
        if not self.always_available:
            return None
        self._publish()
        return ("always_on", 101)

    def create_scheduled_task(self, command):
        self.events.append(("api", "create_schedule", command))
        self.commands.append(command)
        if not self.schedule_available:
            return None
        self._publish()
        return ("schedule", 202)

    def delete_trigger(self, trigger):
        self.events.append(("api", "delete_trigger", trigger))
        self.deleted_triggers.append(trigger)


def pass_receipt():
    source_entries = []
    for index, path in enumerate(ctrl.REMOTE_SOURCES, 1):
        source_entries.append(
            {
                "path": path,
                "sha256": ("%064x" % index),
                "size": 100 + index,
                "line_count": 10 + index,
                "anchors": [
                    {
                        "line": 2,
                        "matches": ["container"],
                        "function": "build_menu",
                        "snippet": "1: def build_menu():\n2:     label = 'Номер контейнера'",
                    }
                ],
            }
        )
    return {
        "task_id": "task_037",
        "mode": "READ_ONLY_DISCOVERY",
        "status": "PASS",
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "ua0009_published": False,
        "sources": source_entries,
        "db": {
            "path": ctrl.REMOTE_DB_PATH,
            "sha256_before": "a" * 64,
            "sha256_after": "a" * 64,
            "quick_check_ok": True,
            "identity_stable": True,
            "candidate_count": 1,
            "matched_table": "cars",
            "matched_id_column": "ua_id",
            "matched_container_column": "container",
            "ua0006_row_count": 1,
        },
        "errors": [],
        "UA0006_CONTAINER_STATUS": "ALREADY_CORRECT",
    }


def blocked_receipt():
    return {
        "task_id": "task_037",
        "mode": "READ_ONLY_DISCOVERY",
        "status": "BLOCKED",
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "ua0009_published": False,
        "sources": [],
        "db": {},
        "errors": ["ua0006_no_match_found"],
    }


class ControllerTestBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = pathlib.Path(
            tempfile.mkdtemp(prefix="task039_controller_")
        )
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.original_evidence = ctrl.EVIDENCE_PATH_LOCAL
        self.original_report = ctrl.REPORT_PATH_LOCAL
        ctrl.EVIDENCE_PATH_LOCAL = (
            self.temp_dir / "evidence" / "task_037_discovery.json"
        )
        ctrl.REPORT_PATH_LOCAL = self.temp_dir / "controller_report.md"
        self.addCleanup(
            setattr, ctrl, "EVIDENCE_PATH_LOCAL", self.original_evidence
        )
        self.addCleanup(
            setattr, ctrl, "REPORT_PATH_LOCAL", self.original_report
        )

        self.events = []
        self.api = FakeAPI(self.events)
        self.env = {
            "PYTHONANYWHERE_USERNAME": "Carix",
            "PYTHONANYWHERE_HOST": "www.pythonanywhere.com",
            "PYTHONANYWHERE_API_TOKEN": "unit-test-value",
        }
        self.clock = {"value": 0.0}

        def runner(command):
            self.events.append(("subprocess", tuple(command)))
            return 0

        def sleep(seconds):
            self.clock["value"] += max(float(seconds), 0.001)

        self.controller = ctrl.DiscoveryController(
            self.api,
            env=self.env,
            subprocess_runner=runner,
            sleep=sleep,
            monotonic=lambda: self.clock["value"],
            utc_now=lambda: NOW,
            poll_interval=0.01,
            poll_timeout=0.05,
        )
        self.seed_valid_manifest()

    def local_hashes(self):
        return {
            source: ctrl.sha256_file(path)
            for source, path in ctrl.LOCAL_ARTIFACTS.items()
        }

    def seed_valid_manifest(self, *, generated_at=None):
        hashes = self.local_hashes()
        entries = []
        for source, digest in hashes.items():
            entries.append(
                {
                    "source": source,
                    "remote": ctrl.REMOTE_ROOT + "/" + source,
                    "bytes": os.path.getsize(ctrl.LOCAL_ARTIFACTS[source]),
                    "sha256": digest,
                    "http_status": 201,
                }
            )
        manifest = {
            "status": "PASS",
            "filter": "claude_latest_status+static_safety",
            "generated_at_utc": (
                generated_at or NOW.isoformat()
            ),
            "repository": "art20021986-wq/ua-art-autopilot",
            "commit": "b" * 40,
            "remote_root": ctrl.REMOTE_ROOT,
            "files_uploaded": len(entries),
            "files": entries,
            "production_touched": False,
            "crm_touched": False,
            "executed_remote_code": False,
            "webapp_reloaded": False,
        }
        self.api.files[ctrl.REMOTE_MANIFEST_PATH] = json.dumps(manifest)
        self.api.files[ctrl.REMOTE_DISCOVERY_SCRIPT] = (
            ctrl.LOCAL_ARTIFACTS[
                "cloud/bot_logistics/bot_logistics_discovery.py"
            ].read_text(encoding="utf-8")
        )
        return manifest

    def set_next_receipt(self, receipt):
        self.api.next_output = (
            receipt if isinstance(receipt, str)
            else json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        )


class TestPassAndBlockedRelay(ControllerTestBase):
    def test_pass_relay(self):
        self.set_next_receipt(pass_receipt())
        result = self.controller.run()
        self.assertEqual(result["status"], "PASS")
        saved = json.loads(ctrl.EVIDENCE_PATH_LOCAL.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "PASS")
        self.assertTrue(ctrl.REPORT_PATH_LOCAL.is_file())

    def test_blocked_relay_is_not_upgraded(self):
        self.set_next_receipt(blocked_receipt())
        result = self.controller.run()
        self.assertEqual(result["status"], "BLOCKED")
        saved = json.loads(ctrl.EVIDENCE_PATH_LOCAL.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "BLOCKED")

    def test_cleanup_on_success(self):
        self.set_next_receipt(pass_receipt())
        self.controller.run()
        self.assertEqual(self.api.deleted_triggers, [("always_on", 101)])
        self.assertEqual(
            self.api.deleted_outputs,
            [ctrl.REMOTE_OUTPUT_PATH, ctrl.REMOTE_OUTPUT_PATH],
        )

    def test_cleanup_on_validation_failure(self):
        receipt = pass_receipt()
        receipt["production_write"] = True
        self.set_next_receipt(receipt)
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()
        self.assertEqual(self.api.deleted_triggers, [("always_on", 101)])
        self.assertEqual(self.api.deleted_outputs[-1], ctrl.REMOTE_OUTPUT_PATH)

    def test_scheduled_fallback_is_one_temporary_trigger(self):
        self.api.always_available = False
        self.set_next_receipt(pass_receipt())
        self.controller.run()
        self.assertEqual(self.api.deleted_triggers, [("schedule", 202)])
        self.assertEqual(
            [event[1] for event in self.events if event[0] == "api"].count(
                "create_schedule"
            ),
            1,
        )


class TestManifestAndLocalGate(ControllerTestBase):
    def test_local_compile_and_tests_run_before_remote_read(self):
        self.set_next_receipt(pass_receipt())
        self.controller.run()
        kinds = [event[0] for event in self.events]
        self.assertEqual(kinds[:2], ["subprocess", "subprocess"])
        commands = [event[1] for event in self.events if event[0] == "subprocess"]
        self.assertIn("py_compile", commands[0])
        self.assertIn("unittest", commands[1])

    def test_manifest_binds_all_four_local_artifacts(self):
        manifest = self.seed_valid_manifest()
        sources = {item["source"] for item in manifest["files"]}
        self.assertEqual(sources, set(ctrl.LOCAL_ARTIFACTS))

    def test_stale_manifest_rejected(self):
        old = NOW - dt.timedelta(seconds=ctrl.MAX_MANIFEST_AGE_SECONDS + 1)
        self.seed_valid_manifest(generated_at=old.isoformat())
        self.set_next_receipt(pass_receipt())
        with self.assertRaisesRegex(ctrl.ControllerError, "manifest_stale"):
            self.controller.run()

    def test_wrong_manifest_sha_rejected(self):
        manifest = self.seed_valid_manifest()
        manifest["files"][0]["sha256"] = "0" * 64
        self.api.files[ctrl.REMOTE_MANIFEST_PATH] = json.dumps(manifest)
        self.set_next_receipt(pass_receipt())
        with self.assertRaisesRegex(ctrl.ControllerError, "manifest_hash_mismatch"):
            self.controller.run()

    def test_wrong_manifest_remote_path_rejected(self):
        manifest = self.seed_valid_manifest()
        manifest["files"][0]["remote"] = "/home/Carix/cars_ui.py"
        self.api.files[ctrl.REMOTE_MANIFEST_PATH] = json.dumps(manifest)
        self.set_next_receipt(pass_receipt())
        with self.assertRaisesRegex(
            ctrl.ControllerError, "manifest_remote_path_mismatch"
        ):
            self.controller.run()

    def test_remote_script_hash_mismatch_rejected(self):
        self.api.files[ctrl.REMOTE_DISCOVERY_SCRIPT] += "\n# changed\n"
        self.set_next_receipt(pass_receipt())
        with self.assertRaisesRegex(
            ctrl.ControllerError, "remote_script_hash_mismatch"
        ):
            self.controller.run()

    def test_manifest_safety_flags_are_exact_false(self):
        manifest = self.seed_valid_manifest()
        manifest["executed_remote_code"] = True
        self.api.files[ctrl.REMOTE_MANIFEST_PATH] = json.dumps(manifest)
        self.set_next_receipt(pass_receipt())
        with self.assertRaisesRegex(
            ctrl.ControllerError, "manifest_safety_field_invalid"
        ):
            self.controller.run()


class TestReceiptRejections(ControllerTestBase):
    def test_stale_preexisting_output_is_deleted(self):
        self.api.files[ctrl.REMOTE_OUTPUT_PATH] = json.dumps(pass_receipt())
        self.api.next_output = None
        with self.assertRaisesRegex(ctrl.ControllerError, "receipt_timeout"):
            self.controller.run()
        self.assertFalse(ctrl.EVIDENCE_PATH_LOCAL.exists())

    def test_stable_malformed_json_rejected(self):
        self.set_next_receipt("{not-json")
        with self.assertRaisesRegex(
            ctrl.ControllerError, "stable_malformed_receipt"
        ):
            self.controller.run()

    def test_duplicate_json_keys_rejected(self):
        self.set_next_receipt(
            '{"task_id":"task_037","task_id":"task_037"}'
        )
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_sensitive_value_rejected(self):
        receipt = blocked_receipt()
        receipt["errors"] = ["api_key=value-that-must-not-leave-host"]
        self.set_next_receipt(receipt)
        with self.assertRaisesRegex(
            ctrl.ControllerError, "receipt_sensitive_data_detected"
        ):
            self.controller.run()

    def test_email_pii_rejected(self):
        receipt = blocked_receipt()
        receipt["errors"] = ["contact person@example.com"]
        self.set_next_receipt(receipt)
        with self.assertRaisesRegex(
            ctrl.ControllerError, "receipt_sensitive_data_detected"
        ):
            self.controller.run()

    def test_live_container_value_field_rejected(self):
        receipt = pass_receipt()
        receipt["current_container"] = "something"
        self.set_next_receipt(receipt)
        with self.assertRaises(ctrl.ControllerError):
            self.controller.run()

    def test_wrong_source_path_rejected(self):
        receipt = pass_receipt()
        receipt["sources"][0]["path"] = "/home/Carix/unapproved.py"
        self.set_next_receipt(receipt)
        with self.assertRaisesRegex(
            ctrl.ControllerError, "receipt_source_path_invalid"
        ):
            self.controller.run()

    def test_pass_requires_all_six_sources(self):
        receipt = pass_receipt()
        receipt["sources"].pop()
        self.set_next_receipt(receipt)
        with self.assertRaisesRegex(
            ctrl.ControllerError, "receipt_sources_incomplete"
        ):
            self.controller.run()

    def test_pass_requires_equal_database_hashes(self):
        receipt = pass_receipt()
        receipt["db"]["sha256_after"] = "c" * 64
        self.set_next_receipt(receipt)
        with self.assertRaisesRegex(
            ctrl.ControllerError, "receipt_db_hash_invalid"
        ):
            self.controller.run()

    def test_blocked_receipt_requires_error(self):
        receipt = blocked_receipt()
        receipt["errors"] = []
        self.set_next_receipt(receipt)
        with self.assertRaisesRegex(
            ctrl.ControllerError, "blocked_receipt_without_error"
        ):
            self.controller.run()

    def test_timeout_rejected(self):
        self.api.next_output = None
        with self.assertRaisesRegex(ctrl.ControllerError, "receipt_timeout"):
            self.controller.run()


class TestExactCommandPathsAndEnvironment(ControllerTestBase):
    def test_exact_command_and_redirection(self):
        self.set_next_receipt(pass_receipt())
        self.controller.run()
        self.assertEqual(self.api.commands, [ctrl.EXACT_EXECUTION_COMMAND])
        self.assertTrue(
            ctrl.EXACT_EXECUTION_COMMAND.startswith(
                "python3.10 /home/Carix/autopilot_inbox/"
            )
        )
        self.assertTrue(
            ctrl.EXACT_EXECUTION_COMMAND.endswith(
                "> " + ctrl.REMOTE_OUTPUT_PATH
            )
        )
        self.assertNotIn("gate_b", ctrl.EXACT_EXECUTION_COMMAND.casefold())

    def test_wrong_username_rejected_before_remote_action(self):
        self.env["PYTHONANYWHERE_USERNAME"] = "Other"
        with self.assertRaisesRegex(ctrl.ControllerError, "invalid_username"):
            self.controller.run()
        self.assertFalse(any(event[0] == "api" for event in self.events))

    def test_wrong_host_rejected_before_remote_action(self):
        self.env["PYTHONANYWHERE_HOST"] = "example.com"
        with self.assertRaisesRegex(ctrl.ControllerError, "invalid_host"):
            self.controller.run()
        self.assertFalse(any(event[0] == "api" for event in self.events))

    def test_missing_token_rejected_before_remote_action(self):
        del self.env["PYTHONANYWHERE_API_TOKEN"]
        with self.assertRaisesRegex(ctrl.ControllerError, "missing_api_token"):
            self.controller.run()
        self.assertFalse(any(event[0] == "api" for event in self.events))

    def test_real_transport_refuses_arbitrary_path_and_command(self):
        def no_network(*args, **kwargs):
            raise AssertionError("network must not be reached")

        api = ctrl.PythonAnywhereAPI(
            username="Carix",
            host="www.pythonanywhere.com",
            token="unit-test-value",
            opener=no_network,
        )
        with self.assertRaisesRegex(
            ctrl.ControllerError, "delete_path_not_allowed"
        ):
            api.delete_output("/home/Carix/crm.db")
        with self.assertRaisesRegex(
            ctrl.ControllerError, "execution_command_not_allowed"
        ):
            api.create_always_on_task("python3.10 /home/Carix/other.py")


class TestWorkflowTemplate(unittest.TestCase):
    def test_workflow_is_installable_and_fail_closed(self):
        path = THIS_DIR / "task037_discovery_workflow.yml.example"
        text = path.read_text(encoding="utf-8")
        self.assertIn(".github/workflows/task037_discovery.yml", text)
        self.assertIn("pythonanywhere_discovery_controller.py", text)
        self.assertNotIn("Reviewed template placeholder", text)
        self.assertIn(
            "cloud/bot_logistics/evidence/task_037_discovery.json", text
        )
        self.assertIn(
            "cloud/bot_logistics/TASK_039_DISCOVERY_CONTROLLER_REPORT.md",
            text,
        )
        self.assertNotIn("run_gate_b", text)
        self.assertNotIn("force-push", text)
        self.assertIn("cancel-in-progress: false", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
