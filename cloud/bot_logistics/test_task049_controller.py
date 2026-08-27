#!/usr/bin/env python3
"""Offline fail-closed tests for the TASK 049 Gate A controller."""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import task049_gate_a_controller as C  # noqa: E402


def pass_receipt():
    return {
        "task_id": "task_049",
        "mode": "GATE_A_ISOLATED_CANDIDATE",
        "status": "PASS",
        "source_path": "/home/Carix/cars_ui.py",
        "candidate_path": C.REMOTE_CANDIDATE,
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "service_reload": False,
        "gate_b_executed": False,
        "ua0009_published": False,
        "errors": [],
        "source_sha256": "06e7da916ea36c4ffafef01c85f59a0574f06d3cdda24aa1f8c242175de726b7",
        "candidate_sha256": "a" * 64,
        "candidate_size": 120000,
        "operations": [
            "centralize_card_keyboard",
            "remove_logistics_from_editor_grid",
            "add_editor_hub_entry",
            "rename_eta_field_label",
            "remove_post_stage_delivery_button",
            "insert_logistics_hub",
            "register_logistics_hub",
        ],
        "checks": {
            "compiled": True,
            "hub_outer_labels": 2,
            "card_entry": 1,
            "editor_entry": 1,
            "hub_handler_registration": 1,
            "hub_stage_action": 1,
            "hub_container_action": 1,
            "hub_days_action": 1,
            "old_delivery_button": 0,
            "old_post_stage_button": 0,
            "old_editor_days": 0,
            "old_editor_container": 0,
        },
        "already_applied": False,
    }


class ControllerTests(unittest.TestCase):
    def test_exact_command_can_only_write_safe_inbox_receipt(self):
        self.assertIn("/home/Carix/autopilot_inbox/", C.EXACT_COMMAND)
        self.assertNotIn("/home/Carix/cars_ui.py >", C.EXACT_COMMAND)
        self.assertNotIn("crm.db", C.EXACT_COMMAND)

    def test_valid_receipt_passes(self):
        self.assertEqual(C.GateAController.validate_receipt(pass_receipt())["status"], "PASS")

    def test_any_production_write_marker_blocks(self):
        for field in (
            "production_write", "crm_write", "db_write", "service_reload",
            "gate_b_executed", "ua0009_published",
        ):
            receipt = pass_receipt()
            receipt[field] = True
            with self.subTest(field=field), self.assertRaises(C.ControllerBlocked):
                C.GateAController.validate_receipt(receipt)

    def test_blocked_remote_gate_is_not_upgraded(self):
        receipt = pass_receipt()
        receipt["status"] = "BLOCKED"
        receipt["errors"] = ["anchor_count"]
        with self.assertRaisesRegex(C.ControllerBlocked, "remote_gate_a_not_pass"):
            C.GateAController.validate_receipt(receipt)

    def test_source_sha_mismatch_blocks(self):
        receipt = pass_receipt()
        receipt["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(C.ControllerBlocked, "source_sha"):
            C.GateAController.validate_receipt(receipt)

    def test_missing_or_duplicate_ui_invariant_blocks(self):
        for key, value in (("card_entry", 0), ("editor_entry", 2), ("old_delivery_button", 1)):
            receipt = pass_receipt()
            receipt["checks"][key] = value
            with self.subTest(key=key), self.assertRaises(C.ControllerBlocked):
                C.GateAController.validate_receipt(receipt)

    def test_unknown_receipt_key_blocks(self):
        receipt = pass_receipt()
        receipt["unexpected"] = "value"
        with self.assertRaisesRegex(C.ControllerBlocked, "unknown_key"):
            C.GateAController.validate_receipt(receipt)

    def test_duplicate_json_key_blocks(self):
        data = b'{"status":"PASS","status":"BLOCKED"}'
        with self.assertRaisesRegex(C.ControllerBlocked, "duplicate_json_key"):
            C.strict_json(data, "test")

    def test_api_refuses_wrong_identity_and_arbitrary_paths(self):
        with self.assertRaisesRegex(C.ControllerBlocked, "invalid_username"):
            C.PythonAnywhereAPI("Other", C.ALLOWED_HOSTS[0], "x")
        api = C.PythonAnywhereAPI(C.ALLOWED_USERNAME, C.ALLOWED_HOSTS[0], "x")
        with self.assertRaisesRegex(C.ControllerBlocked, "remote_file_path_not_allowed"):
            api._file_url("/home/Carix/cars_ui.py")

    def test_strict_json_object_only(self):
        with self.assertRaisesRegex(C.ControllerBlocked, "json_not_object"):
            C.strict_json(json.dumps([1, 2]).encode(), "test")


if __name__ == "__main__":
    unittest.main()

