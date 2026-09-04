#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
import autostart_intake as AI  # noqa: E402
import control_plane as CP  # noqa: E402


NOW = dt.datetime(2026, 9, 4, 14, 0, tzinfo=dt.timezone.utc)


class AutostartIntakeTests(unittest.TestCase):
    def write_mode(self, root: pathlib.Path) -> None:
        activated = "2026-09-04T13:51:01Z"
        for relative in CP.RUNTIME_PINNED_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture:" + relative + "\n", encoding="utf-8")
        runtime = {
            "files": {
                relative: CP.sha256_file(root / relative)
                for relative in CP.RUNTIME_PINNED_PATHS
            },
            "generated_at": activated,
            "mode_epoch": "auto-20260904T135101Z-testfixture0001",
            "schema_version": CP.RUNTIME_MANIFEST_SCHEMA,
        }
        CP.atomic_json(root / CP.RUNTIME_MANIFEST_PATH, runtime)
        runtime_sha = CP.sha256_file(root / CP.RUNTIME_MANIFEST_PATH)
        receipt_rel = "state/receipts/TASK107-R2.json"
        receipt = {
            "task_id": "TASK107-R2",
            "status": "FINISHED",
            "canary_result": "3/3 PASS",
            "tests": "PASS",
            "rollback_drill": "PASS",
            "unexpected_changes": 0,
            "production_touched": False,
        }
        CP.atomic_json(root / receipt_rel, receipt)
        approval_rel = "tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json"
        approval = {
            "allow_replay_existing_launch_markers": False,
            "approved_at": activated,
            "automatic_nonproduction": True,
            "automatic_production": True,
            "mode_epoch": "auto-20260904T135101Z-testfixture0001",
            "owner": "Артём Бровинский / UA ART COMPANY LLC",
            "owner_authorized": True,
            "owner_command": "Включай глобальный продакшн автопилот.",
            "production_requires_backup": True,
            "production_requires_exact_launch": True,
            "production_requires_gate_b": True,
            "production_requires_live_receipt": True,
            "production_requires_owner_approval": True,
            "production_requires_pre_post_health": True,
            "runtime_manifest_path": CP.RUNTIME_MANIFEST_PATH,
            "runtime_manifest_sha256": runtime_sha,
            "schema_version": CP.AUTOMATIC_APPROVAL_SCHEMA,
            "stop_on_safety_failure": True,
            "task107_receipt_path": receipt_rel,
            "task107_receipt_sha256": CP.sha256_file(root / receipt_rel),
            "task_id": "TASK107-R2-AUTOMATIC-MODE",
        }
        CP.atomic_json(root / approval_rel, approval)
        (root / "state/MANUAL_MODE.md").write_text("STATUS: INACTIVE\n", encoding="utf-8")
        mode = {
            "activated_at": activated,
            "allow_replay_existing_launch_markers": False,
            "automatic_nonproduction": True,
            "automatic_production": True,
            "mode_epoch": "auto-20260904T135101Z-testfixture0001",
            "mode": "AUTOMATIC",
            "owner_approval_path": approval_rel,
            "owner_approval_sha256": CP.sha256_file(root / approval_rel),
            "production_requires_backup": True,
            "production_requires_exact_launch": True,
            "production_requires_gate_b": True,
            "production_requires_live_receipt": True,
            "production_requires_owner_approval": True,
            "production_requires_pre_post_health": True,
            "runtime_manifest_path": CP.RUNTIME_MANIFEST_PATH,
            "runtime_manifest_sha256": runtime_sha,
            "schema_version": CP.EXECUTION_MODE_SCHEMA,
            "stop_on_safety_failure": True,
            "task107_receipt_path": receipt_rel,
            "task107_receipt_sha256": CP.sha256_file(root / receipt_rel),
        }
        CP.atomic_json(root / "state/EXECUTION_MODE.json", mode)

    def write_request(
        self,
        root: pathlib.Path,
        task_id: str = "TASK-AUTO-1",
        *,
        production: bool = False,
        critical: dict | None = None,
    ) -> tuple[str, str]:
        value = {
            "task_id": task_id,
            "title": "Exact automatic intake canary",
            "description": "bounded test",
            "changed_paths": ["cloud/%s/result.txt" % task_id.lower()],
            "production_required": production,
            "read_only": False,
            "complexity": 1,
            "ai_requested": False,
            "control_plane_version": "TASK107-R2",
            "execution": {
                "controller_path": "automation/packages/test/controller.py",
                "controller_sha256": "a" * 64,
                "test_paths": ["automation/packages/test/test_controller.py"],
                "file_sha256": {"automation/packages/test/test_controller.py": "b" * 64},
                "receipt_path": "state/receipts/%s.json" % task_id,
                "evidence_paths": ["state/receipts/%s.json" % task_id],
                "production_required": production,
            },
        }
        if critical is not None:
            value["critical"] = critical
        if production:
            value["health_checks"] = ["https://example.test/health"]
            value["storage_probe"] = {
                "evidence_path": "state/storage/production.json",
                "evidence_sha256": "c" * 64,
            }
        rel = "tasks/requests/%s.json" % task_id
        CP.atomic_json(root / rel, value)
        return rel, CP.sha256_file(root / rel)

    def write_launch(
        self,
        root: pathlib.Path,
        request_rel: str,
        request_sha: str,
        task_id: str = "TASK-AUTO-1",
        *,
        production_allowed: bool = False,
        created_at: str = "2026-09-04T13:55:00Z",
        expires_at: str = "2026-09-04T14:55:00Z",
        nonce: str = "nonce-1234567890-abcd",
    ) -> str:
        rel = "tasks/launch/AUTO-%s.json" % task_id
        marker = {
            "action": "RUN_EXACT_TASK",
            "created_at": created_at,
            "expires_at": expires_at,
            "nonce": nonce,
            "mode_epoch": "auto-20260904T135101Z-testfixture0001",
            "owner_authorized": True,
            "production_allowed": production_allowed,
            "request_path": request_rel,
            "request_sha256": request_sha,
            "schema_version": AI.LAUNCH_SCHEMA,
            "task_id": task_id,
        }
        CP.atomic_json(root / rel, marker)
        return rel

    def prepared_nonproduction(self, root: pathlib.Path) -> tuple[str, str]:
        self.write_mode(root)
        request_rel, request_sha = self.write_request(root)
        return self.write_launch(root, request_rel, request_sha), request_sha

    def prepared_production(self, root: pathlib.Path) -> tuple[str, str]:
        self.write_mode(root)
        task_id = "TASK-AUTO-PROD"
        package = root / "automation/packages/test"
        package.mkdir(parents=True, exist_ok=True)
        controller_rel = "automation/packages/test/controller.py"
        test_rel = "automation/packages/test/test_controller.py"
        rollback_rel = "automation/packages/test/rollback.py"
        backup_rel = "automation/packages/test/backup.py"
        (root / controller_rel).write_text("print('controller')\n", encoding="utf-8")
        (root / test_rel).write_text("print('test')\n", encoding="utf-8")
        (root / rollback_rel).write_text("print('rollback')\n", encoding="utf-8")
        (root / backup_rel).write_text("print('backup')\n", encoding="utf-8")
        owner_rel = "tasks/approvals/TASK-AUTO-PROD.production.json"
        changed = "cloud/task-auto-prod/result.txt"
        manifest_rel = "tasks/manifests/TASK-AUTO-PROD.json"
        manifest = {
            "backup_required": True,
            "contract_id": AI.ca.CONTRACT_ID,
            "live_verify_required": True,
            "operations": [{"action": "noop", "path": changed}],
            "protected_paths": ["crm.db", "video/UA-0009.html"],
            "rollback_required": True,
            "task_class": "CRITICAL",
            "task_id": task_id,
        }
        CP.atomic_json(root / manifest_rel, manifest)
        manifest_sha = hashlib.sha256(CP.canonical_json(manifest)).hexdigest()
        gate_rel = "tasks/gates/TASK-AUTO-PROD.json"
        gate = {
            "backup_plan_ready": True,
            "contract_id": AI.ca.CONTRACT_ID,
            "manifest_sha256": manifest_sha,
            "production_write": False,
            "protected_snapshot": {"crm.db": {"sha256": "d" * 64}},
            "rollback_plan_ready": True,
            "status": "PASS",
            "task_id": task_id,
            "tests": "PASS",
            "unexpected_changes": 0,
        }
        CP.atomic_json(root / gate_rel, gate)
        critical = {
            "allow_crm_vehicle_data": False,
            "gate_a_path": gate_rel,
            "gate_a_sha256": CP.sha256_file(root / gate_rel),
            "gate_b_authorized": True,
            "manifest_path": manifest_rel,
            "manifest_sha256": manifest_sha,
            "owner_approval_path": owner_rel,
            "owner_approval_sha256": "0" * 64,
        }
        request_rel, _ = self.write_request(root, task_id, production=True, critical=critical)
        raw = CP.read_json(root / request_rel)
        raw["requested_min_class"] = "CRITICAL"
        raw["changed_paths"] = [changed]
        raw["execution"].update({
            "backup_controller_path": backup_rel,
            "backup_controller_sha256": CP.sha256_file(root / backup_rel),
            "backup_receipt_path": "state/receipts/TASK-AUTO-PROD-BACKUP.json",
            "controller_path": controller_rel,
            "controller_sha256": CP.sha256_file(root / controller_rel),
            "test_paths": [test_rel],
            "file_sha256": {test_rel: CP.sha256_file(root / test_rel)},
            "rollback_controller_path": rollback_rel,
            "rollback_controller_sha256": CP.sha256_file(root / rollback_rel),
            "rollback_receipt_path": "state/receipts/TASK-AUTO-PROD-ROLLBACK.json",
        })
        raw["execution"]["evidence_paths"].append(
            "state/receipts/TASK-AUTO-PROD-ROLLBACK.json"
        )
        raw["execution"]["evidence_paths"].append(
            "state/receipts/TASK-AUTO-PROD-BACKUP.json"
        )
        approval = {
            "approved_at": "2026-09-04T13:53:00Z",
            "authorization_id": "prod-auth-task-auto-prod-0001",
            "authorized_environment": "production",
            "expires_at": "2026-09-04T14:55:00Z",
            "gate_a_sha256": raw["critical"]["gate_a_sha256"],
            "launch_nonce": "nonce-prod-1234567890",
            "manifest_sha256": manifest_sha,
            "mode_epoch": "auto-20260904T135101Z-testfixture0001",
            "owner": "Артём Бровинский / UA ART COMPANY LLC",
            "owner_authorized": True,
            "production_allowed": True,
            "request_path": request_rel,
            "request_subject_sha256": AI.request_authorization_sha256(raw),
            "schema_version": AI.PRODUCTION_AUTHORIZATION_SCHEMA,
            "task_id": task_id,
        }
        CP.atomic_json(root / owner_rel, approval)
        raw["critical"]["owner_approval_sha256"] = CP.sha256_file(root / owner_rel)
        CP.atomic_json(root / request_rel, raw)
        request_sha = CP.sha256_file(root / request_rel)
        launch = self.write_launch(
            root,
            request_rel,
            request_sha,
            task_id=task_id,
            production_allowed=True,
            nonce="nonce-prod-1234567890",
        )
        return launch, request_sha

    def test_valid_new_nonproduction_marker_is_consumed_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            launch, request_sha = self.prepared_nonproduction(root)
            result = AI.consume_launch(launch, "run-1", "a" * 40, root=root, now=NOW)
            self.assertFalse(result["production_required"])
            self.assertEqual(result["request_sha256"], request_sha)
            self.assertTrue((root / result["ledger_path"]).is_file())
            claim = CP.claim_request(
                result["request_path"],
                "run-1",
                root=root,
                expected_request_sha256=request_sha,
                autostart_ledger_path=result["ledger_path"],
                autostart_source_commit="a" * 40,
            )
            self.assertTrue(claim["automatic_mode_enabled"])
            self.assertEqual(claim["autostart_ledger_path"], result["ledger_path"])
            with self.assertRaisesRegex(AI.AutostartIntakeError, "AUTOSTART_REPLAY_BLOCKED"):
                AI.validate_launch(launch, "run-2", "b" * 40, root=root, now=NOW)

    def test_consumed_marker_expiry_is_rechecked_before_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            launch, request_sha = self.prepared_nonproduction(root)
            result = AI.consume_launch(launch, "run-1", "a" * 40, root=root, now=NOW)
            expired = (
                dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            marker = CP.read_json(root / launch)
            marker["expires_at"] = expired
            CP.atomic_json(root / launch, marker)
            ledger_path = root / result["ledger_path"]
            ledger = CP.read_json(ledger_path)
            ledger["expires_at"] = expired
            ledger["launch_sha256"] = CP.sha256_file(root / launch)
            CP.atomic_json(ledger_path, ledger)
            with self.assertRaisesRegex(CP.ControlPlaneError, "AUTOSTART_LEDGER_EXPIRED"):
                CP.claim_request(
                    result["request_path"],
                    "run-1",
                    root=root,
                    expected_request_sha256=request_sha,
                    autostart_ledger_path=result["ledger_path"],
                    autostart_source_commit="a" * 40,
                )

    def test_wrong_request_sha_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_mode(root)
            request_rel, _ = self.write_request(root)
            launch = self.write_launch(root, request_rel, "f" * 64)
            with self.assertRaisesRegex(AI.AutostartIntakeError, "AUTOSTART_REQUEST_SHA_MISMATCH"):
                AI.validate_launch(launch, "run-1", "a" * 40, root=root, now=NOW)

    def test_marker_before_activation_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_mode(root)
            request_rel, request_sha = self.write_request(root)
            launch = self.write_launch(
                root,
                request_rel,
                request_sha,
                created_at="2026-09-04T13:50:00Z",
                expires_at="2026-09-04T14:30:00Z",
            )
            with self.assertRaisesRegex(AI.AutostartIntakeError, "AUTOSTART_MARKER_PREDATES_ACTIVATION"):
                AI.validate_launch(launch, "run-1", "a" * 40, root=root, now=NOW)

    def test_expired_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_mode(root)
            request_rel, request_sha = self.write_request(root)
            launch = self.write_launch(
                root,
                request_rel,
                request_sha,
                created_at="2026-09-04T13:52:00Z",
                expires_at="2026-09-04T13:59:00Z",
            )
            with self.assertRaisesRegex(AI.AutostartIntakeError, "AUTOSTART_MARKER_EXPIRED"):
                AI.validate_launch(launch, "run-1", "a" * 40, root=root, now=NOW)

    def test_existing_receipt_blocks_reexecution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            launch, _ = self.prepared_nonproduction(root)
            CP.atomic_json(root / "state/receipts/TASK-AUTO-1.json", {"status": "FINISHED"})
            with self.assertRaisesRegex(AI.AutostartIntakeError, "AUTOSTART_REQUEST_ALREADY_HAS_RECEIPT"):
                AI.validate_launch(launch, "run-1", "a" * 40, root=root, now=NOW)

    def test_automatic_claim_without_consumed_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_mode(root)
            request_rel, request_sha = self.write_request(root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "AUTOSTART_LEDGER_PATH_MISMATCH"):
                CP.claim_request(
                    request_rel,
                    "run-1",
                    root=root,
                    expected_request_sha256=request_sha,
                )

    def test_production_must_be_critical(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_mode(root)
            request_rel, request_sha = self.write_request(root, production=True)
            launch = self.write_launch(root, request_rel, request_sha, production_allowed=True)
            with self.assertRaisesRegex(AI.AutostartIntakeError, "AUTOSTART_PRODUCTION_MUST_BE_CRITICAL"):
                AI.validate_launch(launch, "run-1", "a" * 40, root=root, now=NOW)

    def test_production_requires_explicit_gate_b(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_mode(root)
            critical = {"gate_b_authorized": False}
            request_rel, request_sha = self.write_request(root, production=True, critical=critical)
            raw = CP.read_json(root / request_rel)
            raw["requested_min_class"] = "CRITICAL"
            CP.atomic_json(root / request_rel, raw)
            request_sha = CP.sha256_file(root / request_rel)
            launch = self.write_launch(root, request_rel, request_sha, production_allowed=True)
            with self.assertRaisesRegex(AI.AutostartIntakeError, "AUTOSTART_PRODUCTION_GATE_B_REQUIRED"):
                AI.validate_launch(launch, "run-1", "a" * 40, root=root, now=NOW)

    def test_valid_production_requires_and_accepts_full_gate_and_rollback_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            launch, request_sha = self.prepared_production(root)
            result = AI.validate_launch(launch, "run-prod", "a" * 40, root=root, now=NOW)
            self.assertTrue(result["production_required"])
            self.assertEqual(result["request_sha256"], request_sha)

    def test_production_owner_approval_must_name_exact_task(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            launch, _ = self.prepared_production(root)
            request = CP.read_json(root / "tasks/requests/TASK-AUTO-PROD.json")
            owner_path = root / request["critical"]["owner_approval_path"]
            owner = CP.read_json(owner_path)
            owner["task_id"] = "DIFFERENT"
            CP.atomic_json(owner_path, owner)
            request["critical"]["owner_approval_sha256"] = CP.sha256_file(owner_path)
            CP.atomic_json(root / "tasks/requests/TASK-AUTO-PROD.json", request)
            marker = CP.read_json(root / launch)
            marker["request_sha256"] = CP.sha256_file(root / "tasks/requests/TASK-AUTO-PROD.json")
            CP.atomic_json(root / launch, marker)
            with self.assertRaisesRegex(
                AI.AutostartIntakeError,
                "AUTOSTART_TASK_SPECIFIC_OWNER_APPROVAL_REQUIRED",
            ):
                AI.validate_launch(launch, "run-prod", "a" * 40, root=root, now=NOW)

    def test_production_owner_explicit_false_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            launch, _ = self.prepared_production(root)
            request_path = root / "tasks/requests/TASK-AUTO-PROD.json"
            request = CP.read_json(request_path)
            owner_path = root / request["critical"]["owner_approval_path"]
            owner = CP.read_json(owner_path)
            owner["production_allowed"] = False
            CP.atomic_json(owner_path, owner)
            request["critical"]["owner_approval_sha256"] = CP.sha256_file(owner_path)
            CP.atomic_json(request_path, request)
            marker = CP.read_json(root / launch)
            marker["request_sha256"] = CP.sha256_file(request_path)
            CP.atomic_json(root / launch, marker)
            with self.assertRaisesRegex(
                AI.AutostartIntakeError, "AUTOSTART_OWNER_PRODUCTION_DENIED"
            ):
                AI.validate_launch(launch, "run-prod", "a" * 40, root=root, now=NOW)


if __name__ == "__main__":
    unittest.main()
