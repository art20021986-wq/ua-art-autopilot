#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
PATH = HERE / "route_canary_controller.py"
spec = importlib.util.spec_from_file_location("task105_route_canary", PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("SPEC")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class RouteCanaryTests(unittest.TestCase):
    def test_paths_are_bounded(self):
        self.assertTrue(str(module.RECEIPT).endswith(
            "state/receipts/TASK105-PERMANENT-ROUTE-CANARY.json"
        ))
        self.assertEqual(module.REPORT.parent, HERE)

    def test_utc_format(self):
        self.assertRegex(module.utc_now(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_atomic_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "a.txt"
            module.atomic_text(path, "ok\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "ok\n")

    def test_main_writes_truthful_nonproduction_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = pathlib.Path(folder) / "receipt.json"
            report = pathlib.Path(folder) / "report.md"
            with mock.patch.object(module, "RECEIPT", receipt), mock.patch.object(
                module, "REPORT", report
            ):
                self.assertEqual(module.main(), 0)
            value = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(value["status"], "FINISHED")
            self.assertEqual(value["task_class"], "FAST")
            self.assertEqual(value["target_environment"], "sandbox")
            self.assertFalse(value["production_required"])
            self.assertEqual(value["unexpected_changes"], 0)
            self.assertTrue(value["rollback_ready"])

    def test_report_declares_no_production(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = pathlib.Path(folder) / "receipt.json"
            report = pathlib.Path(folder) / "report.md"
            with mock.patch.object(module, "RECEIPT", receipt), mock.patch.object(
                module, "REPORT", report
            ):
                module.main()
            text = report.read_text(encoding="utf-8")
            self.assertIn("Production touched: NO", text)
            self.assertIn("CRM/vehicle data touched: NO", text)


if __name__ == "__main__":
    unittest.main()
