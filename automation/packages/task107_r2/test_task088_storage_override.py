#!/usr/bin/env python3
"""The owner's TASK088 waiver cannot change unrelated gates or request scope."""
from __future__ import annotations

import copy
import datetime as dt
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
import control_plane as CP


class Task088StorageOverrideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.task = "TASK088-GE-PRICE-CRM-PREFLIGHT"
        self.relative = "tasks/requests/" + self.task + "-TEST.json"
        for relative in (*CP.RUNTIME_PINNED_PATHS, CP.RUNTIME_ACTIVATION_PATH,
                         CP.RUNTIME_PREVIOUS_MANIFEST_PATH, CP.RUNTIME_PREVIOUS_MODE_PATH,
                         "tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json",
                         "state/receipts/TASK107-R2.json", "state/MANUAL_MODE.md"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        for target, fallback in ((CP.TASK088_PREVIOUS_MODE_PATH, "state/EXECUTION_MODE.json"),
                                 (CP.TASK088_PREVIOUS_MANIFEST_PATH, CP.RUNTIME_MANIFEST_PATH)):
            source = ROOT / target
            if not source.is_file():
                source = ROOT / fallback
            shutil.copyfile(source, self.root / target)
        self.old_mode = CP.read_json(self.root / CP.TASK088_PREVIOUS_MODE_PATH)
        self.runtime = CP.read_json(self.root / CP.TASK088_PREVIOUS_MANIFEST_PATH)
        self.runtime["files"]["automation/control_plane.py"] = CP.sha256_file(ROOT / "automation/control_plane.py")
        self.runtime["generated_at"] = CP.utc_now()
        self.write(CP.RUNTIME_MANIFEST_PATH, self.runtime)
        self.mode = copy.deepcopy(self.old_mode)
        self.mode["runtime_activation_path"] = CP.TASK088_ACTIVATION_PATH
        self.mode["runtime_manifest_sha256"] = CP.sha256_file(self.root / CP.RUNTIME_MANIFEST_PATH)
        self.evidence_path = "state/storage/TASK088-OWNER-STORAGE-OVERRIDE-20260911.json"
        self.write(self.evidence_path, {
            "schema_version": "UA-ART-TASK088-STORAGE-OVERRIDE-EVIDENCE-1",
            "status": "OWNER_OVERRIDE", "task_scope": list(CP.TASK088_PACKAGE_ROOTS),
            "owner_authorized": True, "capacity_measured": False,
            "reason": "Так может быть сними эту непонятную блокировку, удали её нахуй.",
            "business_targets": list(CP.TASK088_TARGET_PATHS),
        })
        self.build_request()
        self.activation = {
            "schema_version": "UA-ART-TASK088-STORAGE-OVERRIDE-1",
            "task_id": "TASK088-STORAGE-OVERRIDE-20260911",
            "scope": "TASK088_CRM_ONLY_STORAGE_OWNER_OVERRIDE",
            "owner": "Артём Бровинский / UA ART COMPANY LLC", "owner_actor_id": "321059821",
            "owner_command": "Так может быть сними эту непонятную блокировку, удали её нахуй.",
            "repository": "art20021986-wq/ua-art-autopilot", "mode_epoch": self.mode["mode_epoch"],
            "runtime_manifest_path": CP.RUNTIME_MANIFEST_PATH,
            "runtime_manifest_sha256": self.mode["runtime_manifest_sha256"],
            "previous_manifest_path": CP.TASK088_PREVIOUS_MANIFEST_PATH,
            "previous_manifest_sha256": CP.TASK088_PREVIOUS_MANIFEST_SHA256,
            "previous_mode_path": CP.TASK088_PREVIOUS_MODE_PATH,
            "previous_mode_sha256": CP.TASK088_PREVIOUS_MODE_SHA256,
            "previous_activation_path": CP.RUNTIME_ACTIVATION_PATH,
            "previous_activation_sha256": CP.TASK088_PREVIOUS_ACTIVATION_SHA256,
            "changed_runtime_paths": ["automation/control_plane.py"],
            "owner_scope_record": copy.deepcopy(CP.TASK088_OWNER_SCOPE),
            "registered_at": CP.utc_now(), "source_commit": "a" * 40,
            "allowed_requests": {},
        }
        self.repin()

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        CP.atomic_json(path, value)

    def build_request(self):
        package = CP.TASK088_PACKAGE_ROOTS[self.task]
        execution = {"production_required": True, "dependency_paths": [], "test_paths": [], "file_sha256": {}}
        for key, filename in (("controller", "controller.py"), ("backup_controller", "backup_controller.py"),
                              ("rollback_controller", "rollback_controller.py")):
            target = self.root / (package + filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# isolated contract fixture\n", encoding="utf-8")
            execution[key + "_path"] = package + filename
            execution[key + "_sha256"] = CP.sha256_file(target)
        execution["backup_receipt_path"] = "state/receipts/" + self.task + "-BACKUP.json"
        execution["rollback_receipt_path"] = "state/receipts/" + self.task + "-ROLLBACK.json"
        self.manifest_path = "tasks/manifests/" + self.task + ".json"
        preflight = self.task.endswith("PREFLIGHT")
        self.manifest = {
            "task_id": self.task, "task_class": "CRITICAL",
            "contract_id": "UA-ART-CRITICAL-ADAPTER-V1.0", "explicit_crm_vehicle_approval": True,
            "operations": [{"path": path, "action": "noop" if preflight else "replace"}
                           for path in CP.TASK088_TARGET_PATHS],
            "backup_required": True, "rollback_required": True, "live_verify_required": True,
        }
        self.raw = {
            "task_id": self.task, "title": "Exact TASK088 fixture", "production_required": True,
            "read_only": preflight, "requested_min_class": "CRITICAL", "changed_paths": list(CP.TASK088_TARGET_PATHS),
            "execution": execution,
            "critical": {"gate_b_authorized": True, "allow_crm_vehicle_data": True,
                         "manifest_path": self.manifest_path},
            "storage_probe": {"evidence_path": self.evidence_path,
                              "evidence_sha256": CP.sha256_file(self.root / self.evidence_path)},
        }

    def repin(self):
        self.write(self.manifest_path, self.manifest)
        manifest_sha = CP.sha256_bytes(CP.canonical_json(self.manifest))
        self.raw["critical"]["manifest_sha256"] = manifest_sha
        self.write(self.relative, self.raw)
        self.request_sha = CP.sha256_file(self.root / self.relative)
        self.binding = {"task_id": self.task, "request_sha256": self.request_sha,
                        "manifest_sha256": manifest_sha,
                        "package_dependency_digest": CP.sha256_bytes(CP.canonical_json(self.raw["execution"]))}
        self.activation["allowed_requests"] = {self.relative: self.binding}
        self.persist_activation()

    def persist_activation(self):
        self.write(CP.TASK088_ACTIVATION_PATH, self.activation)
        self.mode["runtime_activation_sha256"] = CP.sha256_file(self.root / CP.TASK088_ACTIVATION_PATH)
        self.write("state/EXECUTION_MODE.json", self.mode)

    def override(self):
        return CP._task088_owner_storage_override(self.relative, self.raw, self.request_sha, root=self.root)

    def test_exact_preflight_waiver_and_full_mode_validation(self):
        self.assertEqual(CP.verify_execution_mode(root=self.root)["status"], "PASS")
        result = self.override()
        self.assertEqual(result["status"], "OWNER_TASK088_STORAGE_OVERRIDE")
        self.assertTrue(result["allowed"])
        self.assertFalse(result["capacity_measured"])
        self.assertTrue(result["backup_required"])
        for invented in ("usage_percent", "free_bytes", "total_bytes"):
            self.assertNotIn(invented, result)

    def test_exact_crm_apply_can_use_same_owner_scope(self):
        self.task = "TASK088-GE-PRICE-CRM-STAGE1"
        self.relative = "tasks/requests/" + self.task + "-TEST.json"
        self.build_request()
        self.repin()
        self.assertEqual(CP.verify_execution_mode(root=self.root)["status"], "PASS")
        self.assertTrue(self.override()["allowed"])

    def test_wrong_request_sha_blocks(self):
        self.request_sha = "0" * 64
        with self.assertRaisesRegex(CP.ControlPlaneError, "REQUEST_IDENTITY"):
            self.override()

    def test_wrong_controller_blocks_even_when_reauthorized_hashes_match(self):
        self.raw["execution"]["controller_path"] = "cloud/task117_remove_crm_stage_buttons/controller.py"
        self.repin()
        with self.assertRaisesRegex(CP.ControlPlaneError, "CONTROLLER_SCOPE"):
            CP.verify_execution_mode(root=self.root)

    def test_controller_bytes_cannot_drift_after_authorization(self):
        (self.root / self.raw["execution"]["controller_path"]).write_text("# changed after pin\n", encoding="utf-8")
        with self.assertRaisesRegex(CP.ControlPlaneError, "CONTROLLER_SHA"):
            CP.verify_execution_mode(root=self.root)

    def test_activation_cannot_authorize_additional_runtime_changes(self):
        self.runtime["files"]["automation/transaction_watchdog.py"] = "f" * 64
        self.write(CP.RUNTIME_MANIFEST_PATH, self.runtime)
        self.mode["runtime_manifest_sha256"] = CP.sha256_file(self.root / CP.RUNTIME_MANIFEST_PATH)
        self.activation["runtime_manifest_sha256"] = self.mode["runtime_manifest_sha256"]
        self.persist_activation()
        with self.assertRaisesRegex(CP.ControlPlaneError, "TASK088_RUNTIME_CHANGE_SCOPE"):
            CP.verify_execution_mode(root=self.root)

    def test_write_preflight_or_extra_target_blocks(self):
        for mutation in ("write", "site", "gate_b", "read_only"):
            with self.subTest(mutation=mutation):
                before_raw, before_manifest = copy.deepcopy(self.raw), copy.deepcopy(self.manifest)
                if mutation == "write":
                    self.manifest["operations"][0]["action"] = "replace"
                elif mutation == "site":
                    self.raw["changed_paths"].append("production/site/index.html")
                elif mutation == "gate_b":
                    self.raw["critical"]["gate_b_authorized"] = False
                else:
                    self.raw["read_only"] = False
                self.repin()
                with self.assertRaises(CP.ControlPlaneError):
                    CP.verify_execution_mode(root=self.root)
                self.raw, self.manifest = before_raw, before_manifest

    def test_backup_rollback_live_verify_are_required(self):
        for key in ("backup_required", "rollback_required", "live_verify_required"):
            with self.subTest(key=key):
                self.manifest[key] = False
                self.repin()
                with self.assertRaisesRegex(CP.ControlPlaneError, "PROTECTIONS_REQUIRED"):
                    self.override()
                self.manifest[key] = True

    def test_mode_policy_and_scope_record_cannot_expand(self):
        self.mode["production_requires_backup"] = False
        self.persist_activation()
        with self.assertRaises(CP.ControlPlaneError):
            CP.verify_execution_mode(root=self.root)
        self.mode["production_requires_backup"] = True
        self.activation["owner_scope_record"]["site_changes_allowed"] = True
        self.persist_activation()
        with self.assertRaisesRegex(CP.ControlPlaneError, "TASK088_ACTIVATION_SCOPE"):
            CP.verify_execution_mode(root=self.root)

    def test_old_activation_history_cannot_be_rewritten(self):
        old = CP.read_json(self.root / CP.RUNTIME_ACTIVATION_PATH)
        old["owner_command"] = "replacement"
        self.write(CP.RUNTIME_ACTIVATION_PATH, old)
        with self.assertRaisesRegex(CP.ControlPlaneError, "PREVIOUS_ACTIVATION_SHA"):
            CP.verify_execution_mode(root=self.root)

    def test_storage_claim_reports_owner_waiver(self):
        claim_path = self.root / "state/claims/fixture.json"
        claim_path.parent.mkdir(parents=True)
        claim = {"heartbeat_sequence": 0, "task_execution_status": "RUNNING"}
        with mock.patch.object(CP, "_load_exact_claim", return_value=(claim_path, claim, self.raw, self.request_sha)):
            result = CP.storage_preflight(self.relative, "run-1", root=self.root)
        self.assertEqual(result["status"], "OWNER_TASK088_STORAGE_OVERRIDE")
        self.assertEqual(CP.read_json(claim_path)["storage_preflight_status"], result["status"])

    def test_unrelated_request_still_requires_real_fresh_storage(self):
        self.assertIsNone(CP._task088_owner_storage_override("tasks/requests/TASK999.json", {}, "0" * 64, root=self.root))
        with self.assertRaisesRegex(CP.ControlPlaneError, "PRODUCTION_TARGET_STORAGE_PROBE_REQUIRED"):
            CP._production_storage_probe({}, root=self.root)
        relative = "state/storage/real-but-stale.json"
        self.write(relative, {"target_environment": "production", "read_only": True,
                              "measured_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat(),
                              "total_bytes": 1000, "used_bytes": 100, "free_bytes": 900})
        with self.assertRaisesRegex(CP.ControlPlaneError, "STALE_OR_FUTURE"):
            CP._production_storage_probe({"storage_probe": {"evidence_path": relative,
                "evidence_sha256": CP.sha256_file(self.root / relative)}}, root=self.root)

    def test_waiver_descriptor_cannot_claim_measured_capacity(self):
        evidence = CP.read_json(self.root / self.evidence_path)
        evidence["capacity_measured"] = True
        self.write(self.evidence_path, evidence)
        self.raw["storage_probe"]["evidence_sha256"] = CP.sha256_file(self.root / self.evidence_path)
        self.repin()
        with self.assertRaisesRegex(CP.ControlPlaneError, "EVIDENCE_CONTENT"):
            self.override()


if __name__ == "__main__":
    unittest.main()
