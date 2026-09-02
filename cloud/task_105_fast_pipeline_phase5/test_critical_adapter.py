#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "automation/critical_adapter.py"

spec = importlib.util.spec_from_file_location("task105_critical_adapter", ADAPTER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("SPEC")
adapter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adapter
spec.loader.exec_module(adapter)


class CriticalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.owner = (
            adapter.OWNER_MARKER
            + "\nFAST → STANDARD → CRITICAL → переключение основного маршрута\n"
            + "обязательные backup, live-проверка и автоматический rollback\n"
        ).encode("utf-8")
        self.manifest = {
            "contract_id": adapter.CONTRACT_ID,
            "task_id": "TASK105-CRITICAL-ADAPTER",
            "task_class": "CRITICAL",
            "operations": [{
                "action": "create",
                "path": "video/task105-critical-canary.txt",
                "expected_before_sha256": None,
                "expected_after_sha256": "a" * 64,
            }],
            "protected_paths": ["crm.db", "video/index.html", "video/katalog.html"],
            "backup_required": True,
            "rollback_required": True,
            "live_verify_required": True,
        }
        self.raw = {
            "task_id": "TASK105-CRITICAL-ADAPTER",
            "title": "Critical adapter acceptance",
            "description": "deployment architecture",
            "changed_paths": ["video/task105-critical-canary.txt"],
            "production_required": True,
            "requested_min_class": "CRITICAL",
            "owner_approval_path": "tasks/task_105_full_completion.md",
            "owner_approval_sha256": adapter.sha256_bytes(self.owner),
            "manifest_path": "cloud/task_105_fast_pipeline_phase5/critical_manifest.json",
            "manifest_sha256": adapter.sha256_json(self.manifest),
            "gate_b_authorized": True,
            "allow_crm_vehicle_data": False,
        }
        self.request = adapter.CriticalRequest.from_mapping(self.raw)
        self.gate_a = {
            "contract_id": adapter.CONTRACT_ID,
            "task_id": self.request.task_id,
            "status": "PASS",
            "production_write": False,
            "tests": "PASS",
            "unexpected_changes": 0,
            "backup_plan_ready": True,
            "rollback_plan_ready": True,
            "manifest_sha256": self.request.manifest_sha256,
            "protected_snapshot": {
                "crm.db": {"sha256": "b" * 64},
                "video/index.html": {"sha256": "c" * 64},
            },
        }

    def good_final(self):
        return {
            "contract_id": adapter.CONTRACT_ID,
            "task_id": self.request.task_id,
            "status": "FINISHED",
            "task_class": "CRITICAL",
            "target_environment": "production",
            "tests": "PASS",
            "backup": "/home/Carix/backups/task105",
            "production": "PASS",
            "live_verify": "PASS",
            "rollback": "PASS",
            "unexpected_changes": 0,
            "protected_files_unchanged": True,
            "crm_unchanged": True,
            "manifest_sha256": self.request.manifest_sha256,
        }

    def test_01_request_accepts(self):
        self.assertEqual(self.request.requested_min_class, "CRITICAL")

    def test_02_request_rejects_noncritical(self):
        raw = dict(self.raw, requested_min_class="STANDARD")
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.CriticalRequest.from_mapping(raw)

    def test_03_request_rejects_unsafe_path(self):
        raw = dict(self.raw, changed_paths=["../crm.db"])
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.CriticalRequest.from_mapping(raw)

    def test_04_owner_accepts(self):
        result = adapter.validate_owner_approval(self.request, self.owner)
        self.assertEqual(result["status"], "PASS")

    def test_05_owner_rejects_sha(self):
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_owner_approval(self.request, self.owner + b"x")

    def test_06_owner_rejects_missing_marker(self):
        raw = dict(self.raw, owner_approval_sha256=adapter.sha256_bytes(b"CRITICAL rollback"))
        req = adapter.CriticalRequest.from_mapping(raw)
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_owner_approval(req, b"CRITICAL rollback")

    def test_07_manifest_accepts(self):
        result = adapter.validate_manifest(self.request, self.manifest)
        self.assertEqual(result["operation_count"], 1)

    def test_08_manifest_rejects_sha(self):
        bad = copy.deepcopy(self.manifest)
        bad["backup_required"] = False
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_manifest(self.request, bad)

    def test_09_manifest_rejects_sensitive(self):
        bad = copy.deepcopy(self.manifest)
        bad["operations"][0]["path"] = "cloudflare/config.json"
        raw = dict(
            self.raw,
            changed_paths=["cloudflare/config.json"],
            manifest_sha256=adapter.sha256_json(bad),
        )
        req = adapter.CriticalRequest.from_mapping(raw)
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_manifest(req, bad)

    def test_10_manifest_rejects_crm_without_approval(self):
        bad = copy.deepcopy(self.manifest)
        bad["operations"][0]["path"] = "crm.db"
        raw = dict(
            self.raw,
            changed_paths=["crm.db"],
            manifest_sha256=adapter.sha256_json(bad),
        )
        req = adapter.CriticalRequest.from_mapping(raw)
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_manifest(req, bad)

    def test_11_manifest_accepts_crm_only_with_double_approval(self):
        good = copy.deepcopy(self.manifest)
        good["operations"][0]["path"] = "crm.db"
        good["protected_paths"] = ["video/index.html", "video/katalog.html"]
        good["explicit_crm_vehicle_approval"] = True
        raw = dict(
            self.raw,
            changed_paths=["crm.db"],
            manifest_sha256=adapter.sha256_json(good),
            allow_crm_vehicle_data=True,
        )
        req = adapter.CriticalRequest.from_mapping(raw)
        result = adapter.validate_manifest(req, good)
        self.assertEqual(result["status"], "PASS")

    def test_12_manifest_rejects_protected_overlap(self):
        bad = copy.deepcopy(self.manifest)
        bad["protected_paths"].append("video/task105-critical-canary.txt")
        raw = dict(self.raw, manifest_sha256=adapter.sha256_json(bad))
        req = adapter.CriticalRequest.from_mapping(raw)
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_manifest(req, bad)

    def test_13_gate_a_accepts(self):
        result = adapter.validate_gate_a(self.request, self.gate_a)
        self.assertEqual(result["status"], "PASS")

    def test_14_gate_a_rejects_production_write(self):
        bad = dict(self.gate_a, production_write=True)
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_gate_a(self.request, bad)

    def test_15_gate_a_rejects_manifest_drift(self):
        bad = dict(self.gate_a, manifest_sha256="d" * 64)
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_gate_a(self.request, bad)

    def test_16_gate_b_accepts(self):
        result = adapter.authorize_gate_b(
            self.request, self.owner, self.manifest, self.gate_a
        )
        self.assertEqual(result["status"], "GATE_B_AUTHORIZED")

    def test_17_gate_b_rejects_missing_owner_flag(self):
        raw = dict(self.raw, gate_b_authorized=False)
        req = adapter.CriticalRequest.from_mapping(raw)
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.authorize_gate_b(req, self.owner, self.manifest, self.gate_a)

    def test_18_final_accepts(self):
        result = adapter.validate_final_receipt(self.request, self.good_final())
        self.assertEqual(result["status"], "FINISHED")

    def test_19_final_rejects_false_finished(self):
        bad = self.good_final()
        bad["live_verify"] = "FAIL"
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_final_receipt(self.request, bad)

    def test_20_final_rejects_protected_drift(self):
        bad = self.good_final()
        bad["protected_files_unchanged"] = False
        with self.assertRaises(adapter.CriticalAdapterError):
            adapter.validate_final_receipt(self.request, bad)

    def test_21_canonical_manifest_sha_stable(self):
        reordered = {key: self.manifest[key] for key in reversed(list(self.manifest))}
        self.assertEqual(
            adapter.sha256_json(reordered),
            adapter.sha256_json(self.manifest),
        )


if __name__ == "__main__":
    unittest.main()
