#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


HERE = pathlib.Path(__file__).resolve().parent
PATH = HERE / "canary_controller.py"
SPEC = importlib.util.spec_from_file_location("task107_r2_canary_controller", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("CANARY_SPEC")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CanaryControllerTests(unittest.TestCase):
    def request(self, root: pathlib.Path, *, production: bool = False) -> tuple[pathlib.Path, dict[str, str]]:
        request = {
            "task_id": "TASK107-R2-CANARY-1-FAST",
            "title": "Exact canary",
            "changed_paths": ["cloud/task_107_r2/fast-canary.txt"],
            "production_required": production,
            "canary_index": 1,
        }
        path = root / "tasks/requests/TASK107-R2-CANARY-1-FAST.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(request) + "\n", encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        environment = {
            "UAART_REQUEST_PATH": "tasks/requests/TASK107-R2-CANARY-1-FAST.json",
            "UAART_TASK_ID": request["task_id"],
            "UAART_TASK_CLASS": "FAST",
            "UAART_REQUEST_SHA256": sha,
            "UAART_RUN_ID": "test-run-1",
            "UAART_RECEIPT_PATH": "state/receipts/TASK107-R2-CANARY-1-FAST.json",
        }
        return path, environment

    def test_rollback_drill_restores_exact_baseline(self):
        value = MODULE.rollback_drill()
        self.assertEqual(value["status"], "PASS")
        self.assertEqual(value["before_sha256"], value["after_sha256"])
        self.assertNotEqual(value["before_sha256"], value["mutation_sha256"])

    def test_execute_writes_exact_nonproduction_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            _, environment = self.request(root)
            receipt = MODULE.execute(environment, root=root)
            self.assertEqual(receipt["status"], "FINISHED")
            self.assertEqual(receipt["task_class"], "FAST")
            self.assertEqual(receipt["rollback_drill"], "PASS")
            self.assertFalse(receipt["production_touched"])
            self.assertFalse(receipt["site_touched"])
            receipt_path = root / environment["UAART_RECEIPT_PATH"]
            self.assertTrue(receipt_path.is_file())
            self.assertEqual(
                json.loads(receipt_path.read_text(encoding="utf-8"))["run_id"],
                "test-run-1",
            )

    def test_request_hash_is_immutable_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            path, environment = self.request(root)
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.CanaryError, "REQUEST_SHA_MISMATCH"):
                MODULE.execute(environment, root=root)

    def test_production_is_impossible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            _, environment = self.request(root, production=True)
            with self.assertRaisesRegex(MODULE.CanaryError, "CANARY_PRODUCTION_FORBIDDEN"):
                MODULE.execute(environment, root=root)

    def test_missing_identity_environment_fails_closed(self):
        with self.assertRaisesRegex(MODULE.CanaryError, "MISSING_ENVIRONMENT"):
            MODULE.required_environment({})


if __name__ == "__main__":
    unittest.main()
