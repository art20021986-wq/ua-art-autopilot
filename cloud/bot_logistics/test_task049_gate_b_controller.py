#!/usr/bin/env python3
"""Offline tests for the bounded TASK 049 Gate B controller."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import task049_gate_b_controller as C  # noqa: E402


OLD = b"old production source\n"
NEW = b"new approved source\n"
TARGET_COMMAND = "python3.10 /home/Carix/start_safe.py"
DB_HASH = "d" * 64


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def install_receipt(status="PASS"):
    return {
        "task_id": "task_049",
        "mode": "GATE_B_INSTALL",
        "status": status,
        "source_path": C.REMOTE_SOURCE,
        "candidate_path": C.REMOTE_CANDIDATE,
        "backup_path": C.REMOTE_BACKUP,
        "production_write": status == "PASS",
        "crm_write": False,
        "db_write": False,
        "service_restart": False,
        "website_write": False,
        "rollback": False,
        "source_sha256_before": digest(OLD),
        "source_sha256_after": digest(NEW),
        "backup_sha256": digest(OLD),
        "db_sha256_before": DB_HASH,
        "db_sha256_after": DB_HASH,
        "ua0006_container_preserved": True,
        "ua0006_sea_date_preserved": True,
        "ua0006_container": "ONEYSELGF1046602",
        "ua0006_sea_date_out": "2026-01-24",
        "checks": {
            "compiled": True,
            "outer_hub_labels": 2,
            "card_entry": 1,
            "editor_entry": 1,
            "handler": 1,
            "old_delivery_button": 0,
            "old_post_stage_button": 0,
            "old_editor_days": 0,
            "old_editor_container": 0,
        },
        "errors": [] if status == "PASS" else ["remote_install_blocked"],
    }


def rollback_receipt():
    return {
        "task_id": "task_049",
        "mode": "GATE_B_ROLLBACK_AFTER_RESTART_FAILURE",
        "status": "PASS",
        "source_path": C.REMOTE_SOURCE,
        "candidate_path": C.REMOTE_CANDIDATE,
        "backup_path": C.REMOTE_BACKUP,
        "production_write": True,
        "crm_write": False,
        "db_write": False,
        "service_restart": False,
        "website_write": False,
        "rollback": True,
        "source_sha256_after": digest(OLD),
        "db_sha256_before": DB_HASH,
        "db_sha256_after": DB_HASH,
        "ua0006_container_preserved": True,
        "ua0006_sea_date_preserved": True,
        "ua0006_container": "ONEYSELGF1046602",
        "ua0006_sea_date_out": "2026-01-24",
        "errors": [],
    }


class FakeAPI:
    def __init__(self, *, install_status="PASS", fail_first_restart=False):
        self.files = {
            C.REMOTE_SOURCE: OLD,
            C.REMOTE_CANDIDATE: NEW,
        }
        self.install_status = install_status
        self.fail_first_restart = fail_first_restart
        self.restart_calls = 0
        self.created_commands = []
        self.deleted_triggers = []
        self.deleted_outputs = []
        self.uploaded = []
        self.next_trigger = 900001

    def upload(self, path, data):
        self.uploaded.append(path)
        self.files[path] = data

    def read_file(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def delete_output(self, path):
        self.deleted_outputs.append(path)
        self.files.pop(path, None)

    def create_trigger(self, command):
        self.created_commands.append(command)
        identifier = self.next_trigger
        self.next_trigger += 1
        if command == C.INSTALL_COMMAND:
            receipt = install_receipt(self.install_status)
            self.files[C.REMOTE_INSTALL_OUTPUT] = json.dumps(receipt).encode()
            if self.install_status == "PASS":
                self.files[C.REMOTE_BACKUP] = OLD
                self.files[C.REMOTE_SOURCE] = NEW
        elif command == C.ROLLBACK_COMMAND:
            self.files[C.REMOTE_ROLLBACK_OUTPUT] = json.dumps(
                rollback_receipt()
            ).encode()
            self.files[C.REMOTE_SOURCE] = OLD
        else:
            raise AssertionError("unexpected command")
        return "always_on", identifier

    def delete_trigger(self, trigger):
        self.deleted_triggers.append(trigger)

    def task(self, identifier):
        if identifier != C.TARGET_TASK_ID:
            raise AssertionError("wrong target")
        return {
            "id": C.TARGET_TASK_ID,
            "command": TARGET_COMMAND,
            "enabled": True,
        }

    def restart_target(self):
        self.restart_calls += 1
        if self.fail_first_restart and self.restart_calls == 1:
            raise C.ControllerBlocked("simulated_restart_failure")
        return 202


class ControllerFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.script = root / "installer.py"
        self.approval = root / "approval.marker"
        self.evidence = root / "evidence.json"
        self.report = root / "report.md"
        self.script.write_text("value = 1\n", encoding="utf-8")
        self.approval.write_text(
            "DECISION: APPROVE\nUSER_REPLY: APPROVE\n", encoding="utf-8"
        )

    @contextlib.contextmanager
    def patched(self):
        with mock.patch.multiple(
            C,
            LOCAL_SCRIPT=self.script,
            LOCAL_APPROVAL=self.approval,
            EVIDENCE=self.evidence,
            REPORT=self.report,
            EXPECTED_SOURCE_SHA=digest(OLD),
            EXPECTED_CANDIDATE_SHA=digest(NEW),
            TARGET_COMMAND_SHA=digest(TARGET_COMMAND.encode()),
        ):
            yield

    def close(self):
        self.temp.cleanup()


class GateBControllerTests(unittest.TestCase):
    def setUp(self):
        self.fx = ControllerFixture()

    def tearDown(self):
        self.fx.close()

    def test_success_installs_restarts_only_target_and_relays_evidence(self):
        api = FakeAPI()
        with self.fx.patched():
            receipt = C.GateBController(api, sleep=lambda _seconds: None).run()
        self.assertEqual(receipt["controller_status"], "PASS")
        self.assertEqual(api.restart_calls, 1)
        self.assertEqual(api.created_commands, [C.INSTALL_COMMAND])
        self.assertEqual(api.files[C.REMOTE_SOURCE], NEW)
        self.assertEqual(api.files[C.REMOTE_BACKUP], OLD)
        self.assertEqual(api.deleted_triggers, [("always_on", 900001)])
        evidence = json.loads(self.fx.evidence.read_text(encoding="utf-8"))
        self.assertEqual(evidence["target_always_on_id"], C.TARGET_TASK_ID)
        self.assertTrue(evidence["restart_accepted"])
        self.assertFalse(evidence["db_write"])
        self.assertFalse(evidence["website_write"])

    def test_restart_failure_rolls_back_and_restarts_original(self):
        api = FakeAPI(fail_first_restart=True)
        controller = C.GateBController(api, sleep=lambda _seconds: None)
        with self.fx.patched(), self.assertRaisesRegex(
            C.ControllerBlocked, "install_rolled_back"
        ):
            controller.run()
        self.assertTrue(controller.relayed)
        self.assertEqual(api.restart_calls, 2)
        self.assertEqual(
            api.created_commands, [C.INSTALL_COMMAND, C.ROLLBACK_COMMAND]
        )
        self.assertEqual(api.files[C.REMOTE_SOURCE], OLD)
        evidence = json.loads(self.fx.evidence.read_text(encoding="utf-8"))
        self.assertEqual(evidence["controller_status"], "ROLLED_BACK")
        self.assertTrue(evidence["rollback"])

    def test_blocked_install_is_relayed_and_never_restarted(self):
        api = FakeAPI(install_status="BLOCKED")
        controller = C.GateBController(api, sleep=lambda _seconds: None)
        with self.fx.patched(), self.assertRaisesRegex(C.ControllerBlocked, "install_not_pass"):
            controller.run()
        self.assertEqual(api.restart_calls, 0)
        self.assertTrue(controller.relayed)
        evidence = json.loads(self.fx.evidence.read_text(encoding="utf-8"))
        self.assertEqual(evidence["controller_status"], "BLOCKED")
        self.assertIn("install_not_pass", evidence["errors"])

    def test_install_receipt_rejects_wrong_paths_or_safety_markers(self):
        with self.fx.patched():
            for field, value in (
                ("source_path", "/home/Carix/other.py"),
                ("candidate_path", "/tmp/candidate"),
                ("backup_path", "/tmp/backup"),
                ("db_write", True),
                ("website_write", True),
            ):
                receipt = install_receipt()
                receipt[field] = value
                with self.subTest(field=field), self.assertRaises(C.ControllerBlocked):
                    C.validate_install_receipt(receipt)

    def test_rollback_receipt_rejects_changed_database_hash(self):
        with self.fx.patched():
            receipt = rollback_receipt()
            receipt["db_sha256_after"] = "e" * 64
            with self.assertRaisesRegex(C.ControllerBlocked, "rollback_db_hash"):
                C.validate_rollback_receipt(receipt)

    def test_api_refuses_arbitrary_paths_commands_and_target_delete(self):
        api = C.PythonAnywhereAPI(C.USERNAME, C.HOSTS[0], "token")
        with self.assertRaisesRegex(C.ControllerBlocked, "file_path_not_allowed"):
            api.file_url("/home/Carix/crm.db")
        with self.assertRaisesRegex(C.ControllerBlocked, "command_not_allowed"):
            api.create_trigger("python3 arbitrary.py")
        with self.assertRaisesRegex(C.ControllerBlocked, "refuse_delete_target"):
            api.delete_trigger(("always_on", C.TARGET_TASK_ID))

    def test_schedule_fallback_is_bounded_and_deletable(self):
        api = C.PythonAnywhereAPI(C.USERNAME, C.HOSTS[0], "token")
        api.request = mock.Mock(side_effect=[
            (403, b""),
            (201, b'{"id": 700001}'),
            (204, b""),
        ])
        trigger = api.create_trigger(C.INSTALL_COMMAND)
        self.assertEqual(trigger, ("schedule", 700001))
        api.delete_trigger(trigger)
        calls = api.request.call_args_list
        self.assertIn("always_on/", calls[0].args[1])
        self.assertIn("schedule/", calls[1].args[1])
        self.assertIn("schedule/700001/", calls[2].args[1])

    def test_target_identity_is_hash_bound(self):
        with self.fx.patched():
            valid = {
                "id": C.TARGET_TASK_ID,
                "command": TARGET_COMMAND,
                "enabled": True,
            }
            self.assertEqual(C.validate_target(valid)["id"], C.TARGET_TASK_ID)
            changed = dict(valid, command=TARGET_COMMAND + " --other")
            with self.assertRaisesRegex(C.ControllerBlocked, "target_command_changed"):
                C.validate_target(changed)


if __name__ == "__main__":
    unittest.main()
