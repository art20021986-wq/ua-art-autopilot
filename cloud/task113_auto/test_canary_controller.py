#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


PATH = pathlib.Path(__file__).with_name("canary_controller.py")
SPEC = importlib.util.spec_from_file_location("task113_auto_canary", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("CANARY_SPEC")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CanaryControllerTests(unittest.TestCase):
    def test_rollback_drill_restores_exact_bytes(self):
        result = MODULE.rollback_drill()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["before"], result["after"])
        self.assertNotEqual(result["before"], result["during"])

    def test_end_to_end_nonproduction_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            original_root = MODULE.ROOT
            MODULE.ROOT = root
            try:
                request_rel = "tasks/requests/TASK113-GLOBAL-AUTO-CANARY.json"
                request_path = root / request_rel
                request_path.parent.mkdir(parents=True)
                request_path.write_text(
                    json.dumps({
                        "task_id": MODULE.TASK_ID,
                        "production_required": False,
                    }) + "\n",
                    encoding="utf-8",
                )
                mode_path = root / "state/EXECUTION_MODE.json"
                mode_path.parent.mkdir(parents=True)
                mode_path.write_text(
                    json.dumps({"mode": "AUTOMATIC", "mode_epoch": "auto-test-epoch-0000001"}) + "\n",
                    encoding="utf-8",
                )
                environment = {
                    "UAART_REQUEST_PATH": request_rel,
                    "UAART_TASK_ID": MODULE.TASK_ID,
                    "UAART_TASK_CLASS": "FAST",
                    "UAART_REQUEST_SHA256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
                    "UAART_RUN_ID": "run-test",
                    "UAART_RECEIPT_PATH": MODULE.RECEIPT_REL,
                }
                receipt = MODULE.run(environment)
                self.assertEqual(receipt["status"], "FINISHED")
                self.assertFalse(receipt["production_touched"])
                self.assertTrue((root / MODULE.RECEIPT_REL).is_file())
                self.assertTrue((root / MODULE.EVIDENCE_REL).is_file())
            finally:
                MODULE.ROOT = original_root


if __name__ == "__main__":
    unittest.main()
