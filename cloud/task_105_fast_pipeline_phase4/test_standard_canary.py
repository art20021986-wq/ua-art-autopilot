#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError("SPEC")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


controller = load_module("task105_standard_controller", "standard_canary_controller.py")
remote = load_module("task105_standard_remote", "standard_canary_remote.py")


class ControllerTests(unittest.TestCase):
    def test_payload_count_and_uniqueness(self):
        values = controller.build_payloads("123", "a" * 40)
        self.assertEqual(set(values), {"a_v1", "a_v2", "b_v1", "b_temp", "c_v1"})
        self.assertEqual(len({controller.sha(v) for v in values.values()}), 5)

    def test_payload_contract(self):
        value = controller.build_payloads("123", "b" * 40)["a_v1"].decode()
        self.assertIn("TASK_ID=TASK105-STANDARD-PRODUCTION-CANARY\n", value)
        self.assertIn("PAYLOAD_KEY=a_v1\n", value)
        self.assertIn("NO_CRM_WRITE=TRUE\n", value)

    def test_public_absent_404(self):
        self.assertEqual(
            controller.classify_public_target(404, b"x", 200, b"home"),
            "ABSENT_404",
        )

    def test_public_absent_home_fallback(self):
        self.assertEqual(
            controller.classify_public_target(200, b"home", 200, b"home"),
            "ABSENT_HOME_FALLBACK",
        )

    def test_public_existing(self):
        self.assertEqual(
            controller.classify_public_target(200, b"marker", 200, b"home"),
            "EXISTING_FILE",
        )

    def test_public_rejects_bad_home(self):
        with self.assertRaises(controller.ControllerError):
            controller.classify_public_target(200, b"x", 500, b"home")

    def good_install(self):
        payloads = controller.build_payloads("123", "c" * 40)
        expected_files = [
            "/home/Carix/video/task105-standard-canary-a.txt",
            "/home/Carix/video/task105-standard-canary-b.txt",
            "/home/Carix/video/task105-standard-canary-c.txt",
        ]
        protected = {"x": {"sha256": "1"}}
        return payloads, {
            "contract_id": controller.CONTRACT_ID,
            "status": "PASS",
            "mode": "INSTALL",
            "production_write": True,
            "crm_write": False,
            "existing_site_file_write": False,
            "cloudflare_write": False,
            "dns_write": False,
            "case_count": 3,
            "cases": [{"status": "PASS"} for _ in range(3)],
            "changed_files": expected_files,
            "backup_root": "/home/Carix/backups/x",
            "backup_manifest": "/home/Carix/backups/x/manifest.json",
            "rollback_ready": True,
            "protected_before": protected,
            "protected_after": protected,
            "unexpected_changes": 0,
            "after": {
                "a": {"existed": True, "sha256": controller.sha(payloads["a_v2"])},
                "b": {"existed": True, "sha256": controller.sha(payloads["b_v1"])},
                "c": {"existed": True, "sha256": controller.sha(payloads["c_v1"])},
            },
        }

    def test_validate_install_accepts_good(self):
        payloads, value = self.good_install()
        controller.validate_install(value, payloads)

    def test_validate_install_rejects_protected_drift(self):
        payloads, value = self.good_install()
        value["protected_after"] = {"x": {"sha256": "2"}}
        with self.assertRaises(controller.ControllerError):
            controller.validate_install(value, payloads)

    def test_validate_install_rejects_case_count(self):
        payloads, value = self.good_install()
        value["case_count"] = 2
        with self.assertRaises(controller.ControllerError):
            controller.validate_install(value, payloads)

    def test_validate_baseline_absent(self):
        baselines = {
            name: {"kind": "ABSENT_HOME_FALLBACK", "sha256": "h"}
            for name in controller.PUBLIC_MARKERS
        }
        before = {
            name: {"existed": False, "sha256": None}
            for name in controller.PUBLIC_MARKERS
        }
        controller.validate_baseline_mapping(baselines, before)

    def test_validate_baseline_existing(self):
        baselines = {
            name: {"kind": "EXISTING_FILE", "sha256": name}
            for name in controller.PUBLIC_MARKERS
        }
        before = {
            name: {"existed": True, "sha256": name}
            for name in controller.PUBLIC_MARKERS
        }
        controller.validate_baseline_mapping(baselines, before)

    def test_postcheck_accepts(self):
        controller.validate_postcheck({
            "contract_id": controller.CONTRACT_ID,
            "status": "PASS",
            "mode": "POSTCHECK",
            "production_write": False,
            "crm_write": False,
            "case_count": 3,
        })

    def test_rollback_accepts(self):
        protected = {"x": {"sha256": "1"}}
        controller.validate_rollback({
            "contract_id": controller.CONTRACT_ID,
            "status": "PASS",
            "mode": "ROLLBACK",
            "production_write": True,
            "crm_write": False,
            "protected_before": protected,
            "protected_after": protected,
            "unexpected_changes": 0,
        })


class RemotePureTests(unittest.TestCase):
    def test_targets_are_dedicated(self):
        self.assertEqual(
            [str(remote.TARGETS[k]) for k in ("a", "b", "c")],
            [
                "/home/Carix/video/task105-standard-canary-a.txt",
                "/home/Carix/video/task105-standard-canary-b.txt",
                "/home/Carix/video/task105-standard-canary-c.txt",
            ],
        )

    def test_protected_set(self):
        self.assertEqual(
            {str(p) for p in remote.PROTECTED},
            {
                "/home/Carix/crm.db",
                "/home/Carix/video/index.html",
                "/home/Carix/video/katalog.html",
            },
        )


if __name__ == "__main__":
    unittest.main()
