#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("SPEC:" + name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_module(
    "task105_standard_recovery_controller_test",
    HERE / "standard_canary_recovery_controller.py",
)


class RecoveryControllerTests(unittest.TestCase):
    def test_cleanup_noop_accepts(self):
        controller.validate_cleanup({
            "contract_id": controller.CONTRACT_ID,
            "status": "PASS",
            "mode": "CLEANUP",
            "production_write": False,
            "crm_write": False,
            "cleanup_needed": False,
        })

    def test_cleanup_write_accepts_when_protected_equal(self):
        protected = {"crm": {"sha256": "a"}}
        controller.validate_cleanup({
            "contract_id": controller.CONTRACT_ID,
            "status": "PASS",
            "mode": "CLEANUP",
            "production_write": True,
            "crm_write": False,
            "cleanup_needed": True,
            "protected_before": protected,
            "protected_after": protected,
            "protected_unchanged": True,
        })

    def test_cleanup_rejects_crm_write(self):
        with self.assertRaises(controller.base.ControllerError):
            controller.validate_cleanup({
                "contract_id": controller.CONTRACT_ID,
                "status": "PASS",
                "mode": "CLEANUP",
                "production_write": False,
                "crm_write": True,
                "cleanup_needed": False,
            })

    def test_cleanup_rejects_protected_drift(self):
        with self.assertRaises(controller.base.ControllerError):
            controller.validate_cleanup({
                "contract_id": controller.CONTRACT_ID,
                "status": "PASS",
                "mode": "CLEANUP",
                "production_write": True,
                "crm_write": False,
                "cleanup_needed": True,
                "protected_before": {"x": 1},
                "protected_after": {"x": 2},
                "protected_unchanged": False,
            })

    def test_remote_paths_are_bounded(self):
        self.assertTrue(controller.REMOTE_BASE.startswith(controller.base.REMOTE + "/"))
        self.assertEqual(controller.REMOTE_BRIDGE, controller.base.REMOTE_SCRIPT)
        self.assertTrue(controller.CLEANUP_RECEIPT.startswith(controller.base.REMOTE + "/"))

    def test_recovery_report_mentions_same_task(self):
        text = controller.report_text({"status": "PASS", "cleanup": {"status": "PASS"}})
        self.assertIn("Same TASK105 identity retained: YES", text)
        self.assertIn("Blind retry: NO", text)
        self.assertIn("Full rollback drill", text)

    def test_bridge_binds_compatible_validator(self):
        source = (HERE / "standard_canary_remote_bridge.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assignments = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
        ]
        rendered = ast.dump(tree)
        self.assertIn("validate_backup_compatible", rendered)
        self.assertTrue(any(
            any(
                isinstance(target, ast.Attribute)
                and target.attr == "validate_backup"
                for target in node.targets
            )
            for node in assignments
        ))

    def test_bridge_supports_cleanup_and_manifest_rewrite(self):
        source = (HERE / "standard_canary_remote_bridge.py").read_text(encoding="utf-8")
        self.assertIn("def run_cleanup", source)
        self.assertIn("def rewrite_full_manifest", source)
        self.assertIn('"cleanup"', source)
        self.assertIn('base.atomic_json(backup_root / "manifest.json", manifest)', source)


if __name__ == "__main__":
    unittest.main()
