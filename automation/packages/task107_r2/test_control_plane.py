#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
PATH = ROOT / "automation/control_plane.py"
SPEC = importlib.util.spec_from_file_location("task107_r2_control_plane", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("CONTROL_PLANE_SPEC")
CP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CP
SPEC.loader.exec_module(CP)


class FakeResponse:
    def __init__(self, status: int = 200, url: str = "https://example.test/health"):
        self.status = status
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self, _amount):
        return b"ok"


class ControlPlaneTests(unittest.TestCase):
    def write_manual_mode(self, root: pathlib.Path) -> None:
        marker = root / "state/MANUAL_MODE.md"
        marker.parent.mkdir(parents=True, exist_ok=True)
        if not (root / "state/EXECUTION_MODE.json").exists():
            marker.write_text("# Test mode\n\nSTATUS: ACTIVE\n", encoding="utf-8")

    def write_automatic_mode(self, root: pathlib.Path) -> dict:
        activated_at = "2026-09-04T13:51:01Z"
        for relative in CP.RUNTIME_PINNED_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture:" + relative + "\n", encoding="utf-8")
        runtime = {
            "files": {
                relative: CP.sha256_file(root / relative)
                for relative in CP.RUNTIME_PINNED_PATHS
            },
            "generated_at": activated_at,
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
            "approved_at": activated_at,
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
        mode = {
            "activated_at": activated_at,
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
        manual = root / "state/MANUAL_MODE.md"
        manual.parent.mkdir(parents=True, exist_ok=True)
        manual.write_text("# Test mode\n\nSTATUS: INACTIVE\n", encoding="utf-8")
        CP.atomic_json(root / "state/EXECUTION_MODE.json", mode)
        return mode

    def write_request(
        self,
        root: pathlib.Path,
        task_id: str,
        *,
        changed_paths=None,
        production=False,
        ai_requested=False,
        health_checks=None,
        storage_probe=None,
        requested_min_class=None,
        critical=None,
    ) -> str:
        self.write_manual_mode(root)
        controller_sha = "a" * 64
        test_sha = "b" * 64
        value = {
            "task_id": task_id,
            "title": "Bounded request",
            "description": "replace exact checksum",
            "changed_paths": changed_paths or ["cloud/%s.txt" % task_id.lower()],
            "production_required": production,
            "read_only": False,
            "complexity": 1,
            "ai_requested": ai_requested,
            "execution": {
                "controller_path": "automation/packages/task107_r2/canary_controller.py",
                "controller_sha256": controller_sha,
                "test_paths": ["automation/packages/task107_r2/test_canary_controller.py"],
                "file_sha256": {
                    "automation/packages/task107_r2/test_canary_controller.py": test_sha,
                },
                "receipt_path": "state/receipts/%s.json" % task_id,
                "evidence_paths": ["state/receipts/%s.json" % task_id],
                "production_required": production,
            },
        }
        if health_checks is not None:
            value["health_checks"] = health_checks
        if storage_probe is not None:
            value["storage_probe"] = storage_probe
        if production and requested_min_class is None:
            value["requested_min_class"] = "CRITICAL"
        elif requested_min_class is not None:
            value["requested_min_class"] = requested_min_class
        if critical is not None:
            value["critical"] = critical
        relative = "tasks/requests/%s.json" % task_id
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return relative

    def test_valid_automatic_mode_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            result = CP.verify_execution_mode(root=root, required_mode="AUTOMATIC")
            self.assertEqual(result["mode"], "AUTOMATIC")
            self.assertTrue(result["automatic_production"])

    def test_automatic_mode_rejects_tampered_task107_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            receipt_path = root / "state/receipts/TASK107-R2.json"
            receipt_path.write_text(receipt_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(CP.ControlPlaneError, "TASK107_RECEIPT_SHA_MISMATCH"):
                CP.verify_execution_mode(root=root)

    def test_automatic_mode_rejects_tampered_owner_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            approval_path = root / "tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json"
            approval_path.write_text(approval_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(CP.ControlPlaneError, "AUTOMATIC_APPROVAL_SHA_MISMATCH"):
                CP.verify_execution_mode(root=root)

    def test_automatic_mode_rejects_tampered_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / CP.RUNTIME_PINNED_PATHS[0]
            target.write_text(target.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(CP.ControlPlaneError, "RUNTIME_PINNED_FILE_SHA_MISMATCH"):
                CP.verify_execution_mode(root=root)

    def test_automatic_mode_requires_manual_marker_inactive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            (root / "state/MANUAL_MODE.md").write_text("STATUS: ACTIVE\n", encoding="utf-8")
            with self.assertRaisesRegex(CP.ControlPlaneError, "MANUAL_MODE_NOT_INACTIVE"):
                CP.verify_execution_mode(root=root)

    def test_exact_intake_uses_requested_path_not_highest_task_number(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            first = self.write_request(root, "TASK-2")
            self.write_request(root, "TASK-999")
            claim = CP.claim_request(first, "run-1", root=root)
            self.assertEqual(claim["identity"]["task_id"], "TASK-2")
            self.assertEqual(claim["request_path"], first)

    def test_claim_rejects_changed_request_when_sha_is_pinned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-PINNED")
            with self.assertRaisesRegex(CP.ControlPlaneError, "CLAIM_REQUEST_SHA_MISMATCH"):
                CP.claim_request(
                    request,
                    "run-1",
                    root=root,
                    expected_request_sha256="f" * 64,
                )

    def test_atomic_duplicate_protection_blocks_second_active_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-DUP")
            CP.claim_request(request, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "DUPLICATE_ACTIVE_CLAIM"):
                CP.claim_request(request, "run-2", root=root)

    def test_same_exact_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-IDEMPOTENT")
            first = CP.claim_request(request, "run-1", root=root)
            second = CP.claim_request(request, "run-1", root=root)
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(first["identity"], second["identity"])

    def test_resource_queue_allows_independent_cards(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            one = self.write_request(root, "TASK-CARD-1", changed_paths=["cards/UA-0001/meta.json"])
            two = self.write_request(root, "TASK-CARD-2", changed_paths=["cards/UA-0002/meta.json"])
            first = CP.claim_request(one, "run-1", root=root)
            second = CP.claim_request(two, "run-2", root=root)
            self.assertNotEqual(first["queue_key"], second["queue_key"])

    def test_resource_queue_blocks_overlapping_control_plane(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            one = self.write_request(root, "TASK-CP-1", changed_paths=[".github/workflows/a.yml"])
            two = self.write_request(root, "TASK-CP-2", changed_paths=[".github/workflows/b.yml"])
            CP.claim_request(one, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "RESOURCE_BUSY"):
                CP.claim_request(two, "run-2", root=root)

    def test_actual_control_plane_path_is_critical(self):
        value = {
            "task_id": "TASK-CLASS",
            "title": "Change pipeline",
            "changed_paths": [".github/workflows/uaart_fast.yml"],
        }
        self.assertEqual(CP.classify_request(value), "CRITICAL")

    def test_ai_response_status_cannot_finish_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-AI", ai_requested=True)
            claim = CP.claim_request(request, "run-1", root=root)
            self.assertEqual(claim["ai_response_status"], "PENDING")
            self.assertEqual(claim["task_execution_status"], "CLAIMED")
            plan_path = root / "state/ai_plans/TASK-AI.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text('{"steps":["review"]}\n', encoding="utf-8")
            plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
            updated = CP.record_ai_plan(
                request,
                "run-1",
                "state/ai_plans/TASK-AI.json",
                plan_sha,
                root=root,
            )
            self.assertEqual(updated["ai_response_status"], "RECEIVED")
            self.assertNotEqual(updated["task_execution_status"], "FINISHED")

    def test_ai_plan_cannot_supply_executable_fields(self):
        with self.assertRaisesRegex(CP.ControlPlaneError, "EXECUTABLE_FIELD_FORBIDDEN"):
            CP.validate_ai_plan({"steps": [{"shell": "rm anything"}]})

    def test_no_ai_planning_is_explicit_and_non_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-NO-AI")
            CP.claim_request(request, "run-1", root=root)
            result = CP.prepare_request_planning(request, "run-1", root=root)
            self.assertEqual(result["status"], "NOT_REQUESTED")
            self.assertFalse(result["executable_content_accepted"])

    def test_storage_thresholds_and_required_space(self):
        self.assertEqual(CP.storage_decision(69.99, 1000, 10, heavy=True)["status"], "PASS")
        self.assertEqual(CP.storage_decision(70, 1000, 10, heavy=True)["status"], "WARN_70")
        self.assertFalse(CP.storage_decision(80, 1000, 10, heavy=True)["allowed"])
        self.assertEqual(CP.storage_decision(90, 1000, 10, heavy=False)["status"], "STOP_90")
        self.assertEqual(
            CP.storage_decision(10, 9, 10, heavy=False)["status"],
            "BLOCK_INSUFFICIENT_FREE_SPACE",
        )

    def test_production_health_is_mandatory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-HEALTH", production=True)
            CP.claim_request(request, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "PRODUCTION_HEALTH_CHECKS_REQUIRED"):
                CP.health_phase(request, "run-1", "pre", root=root)

    def test_production_cannot_route_fast_or_standard(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-PROD-CLASS", production=True)
            raw = CP.read_json(root / request)
            raw.pop("requested_min_class")
            CP.atomic_json(root / request, raw)
            with self.assertRaisesRegex(CP.ControlPlaneError, "PRODUCTION_MUST_ROUTE_CRITICAL"):
                CP.claim_request(request, "run-1", root=root)

    def test_production_storage_requires_target_probe_not_runner_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-STORAGE-PROD", production=True)
            CP.claim_request(request, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "TARGET_STORAGE_PROBE_REQUIRED"):
                CP.storage_preflight(request, "run-1", root=root)

    def test_recent_pinned_production_storage_probe_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            probe_rel = "state/storage/production.json"
            probe_path = root / probe_rel
            probe_path.parent.mkdir(parents=True)
            probe = {
                "target_environment": "production",
                "read_only": True,
                "measured_at": CP.utc_now(),
                "total_bytes": 1_000_000_000,
                "used_bytes": 600_000_000,
                "free_bytes": 400_000_000,
            }
            probe_path.write_text(json.dumps(probe, sort_keys=True) + "\n", encoding="utf-8")
            probe_sha = hashlib.sha256(probe_path.read_bytes()).hexdigest()
            request = self.write_request(
                root,
                "TASK-STORAGE-PROD-PASS",
                production=True,
                storage_probe={"evidence_path": probe_rel, "evidence_sha256": probe_sha},
            )
            CP.claim_request(request, "run-1", root=root)
            result = CP.storage_preflight(request, "run-1", root=root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["measurement_scope"], "production_target_read_only_probe")

    def test_pre_and_post_health_record_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(
                root,
                "TASK-HEALTH-PASS",
                production=True,
                health_checks=["https://example.test/health"],
            )
            CP.claim_request(request, "run-1", root=root)

            def opener(_request, timeout):
                self.assertGreater(timeout, 0)
                return FakeResponse()

            self.assertEqual(CP.health_phase(request, "run-1", "pre", root=root, opener=opener)["status"], "PASS")
            self.assertEqual(CP.health_phase(request, "run-1", "post", root=root, opener=opener)["status"], "PASS")

    def test_stall_detector_marks_old_active_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-STALL")
            result = CP.claim_request(request, "run-1", root=root)
            claim_path = root / result["claim_path"]
            claim = CP.read_json(claim_path)
            claim["heartbeat_at"] = "2026-01-01T00:00:00Z"
            CP.atomic_json(claim_path, claim)
            now = dt.datetime(2026, 1, 1, 0, 10, tzinfo=dt.timezone.utc)
            state = CP.detect_stall(claim_path, 60, now=now)
            self.assertTrue(state["stalled"])
            self.assertEqual(state["task_execution_status"], "STALLED")

    def test_durable_production_transaction_can_be_recovered_after_finish_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request_rel = "tasks/requests/TASK-TX.json"
            raw = {
                "task_id": "TASK-TX",
                "title": "Transaction test",
                "production_required": True,
                "execution": {
                    "backup_receipt_path": "state/receipts/TASK-TX-BACKUP.json"
                },
            }
            CP.atomic_json(root / request_rel, raw)
            request_sha = CP.sha256_file(root / request_rel)
            identity = CP._identity(raw, request_sha, "run-tx")
            claim_path = root / CP.claim_relative_path(identity)
            ledger_rel = "state/autostart_consumed/tx.json"
            CP.atomic_json(root / ledger_rel, {"expires_at": "2099-01-01T00:00:00Z"})
            backup_rel = raw["execution"]["backup_receipt_path"]
            CP.atomic_json(root / backup_rel, {"status": "PASS"})
            claim = {
                "autostart_ledger_path": ledger_rel,
                "critical_gate_status": "PASS_PRODUCTION",
                "execution_mode": "AUTOMATIC",
                "identity": identity,
                "mode_epoch": "auto-test-1234567890123456",
                "package_compile_status": "PASS",
                "pre_health_status": "PASS",
                "request_path": request_rel,
                "storage_preflight": {"allowed": True},
                "task_execution_status": "RUNNING",
            }
            CP.atomic_json(claim_path, claim)
            transaction_id = "tx-run-tx-abcdef0123456789"
            with mock.patch.object(
                CP,
                "_load_exact_claim",
                return_value=(claim_path, claim, raw, request_sha),
            ):
                opened = CP.open_production_transaction(
                    request_rel,
                    "run-tx",
                    transaction_id,
                    CP.sha256_file(root / backup_rel),
                    "a" * 64,
                    root=root,
                )
            self.assertEqual(opened["status"], "OPEN")
            finished = CP.close_production_transaction(
                request_rel, "run-tx", transaction_id, "FINISHED", root=root
            )
            self.assertEqual(finished["status"], "FINISHED")
            recovered = CP.close_production_transaction(
                request_rel, "run-tx", transaction_id, "ROLLED_BACK", root=root
            )
            self.assertEqual(recovered["status"], "ROLLED_BACK")

    def test_retry_is_bounded_and_logical_failure_enters_root_cause(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-RETRY")
            CP.claim_request(request, "run-1", root=root)
            transient = CP.record_failure(request, "run-1", "HTTP 503 temporary", root=root)
            self.assertTrue(transient["retry_allowed"])
            logical = CP.record_failure(request, "run-1", "SyntaxError line 1", root=root)
            self.assertFalse(logical["retry_allowed"])
            logical_again = CP.record_failure(request, "run-1", "SyntaxError line 1", root=root)
            self.assertEqual(logical_again["action"], "ROOT_CAUSE_MODE")

    def test_finished_requires_exact_validated_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-FINISH")
            claim = CP.claim_request(request, "run-1", root=root)
            CP.storage_preflight(request, "run-1", root=root, usage_percent=10, free_bytes=10**9)
            CP.mark_compiled(request, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "INVALID_JSON"):
                CP.finish_request(request, "run-1", root=root)
            receipt_path = root / "state/receipts/TASK-FINISH.json"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt = {
                "task_id": "TASK-FINISH",
                "status": "FINISHED",
                "task_class": "FAST",
                "target_environment": "sandbox",
                "tests": "PASS",
                "unexpected_changes": 0,
                "rollback_ready": True,
                "production_required": False,
                "request_sha256": claim["request_sha256"],
                "run_id": "run-1",
            }
            receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            finished = CP.finish_request(request, "run-1", root=root)
            self.assertEqual(finished["task_execution_status"], "FINISHED")
            self.assertEqual(finished["receipt_validation_status"], "PASS")

    def test_autostart_guard_matches_exact_identity_not_recent_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-GUARD")
            claim = CP.claim_request(request, "run-1", root=root)
            passed = CP.verify_exact_identity(
                request,
                "TASK-GUARD",
                claim["request_sha256"],
                "run-1",
                root=root,
            )
            self.assertFalse(passed["generic_recent_run_accepted"])
            with self.assertRaisesRegex(CP.ControlPlaneError, "AUTOSTART_TASK_ID_MISMATCH"):
                CP.verify_exact_identity(
                    request,
                    "TASK-OTHER",
                    claim["request_sha256"],
                    "run-1",
                    root=root,
                )

    def test_nonproduction_critical_gate_is_separate_from_gate_b(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            task_id = "TASK-CRITICAL"
            owner_rel = "tasks/approvals/critical.md"
            manifest_rel = "tasks/manifests/critical.json"
            gate_rel = "tasks/gates/critical.json"
            owner_path = root / owner_rel
            owner_path.parent.mkdir(parents=True)
            owner_path.write_text(
                "%s TASK107-R2 OWNER_APPROVED MANUAL_ONLY\n" % task_id,
                encoding="utf-8",
            )
            changed = [".github/workflows/uaart_orchestrator.yml"]
            manifest = {
                "task_id": task_id,
                "task_class": "CRITICAL",
                "operations": [{"action": "noop", "path": changed[0]}],
                "protected_paths": ["crm.db", "video/UA-0009.html"],
                "rollback_required": True,
            }
            manifest_path = root / manifest_rel
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            manifest_sha = hashlib.sha256(CP.canonical_json(manifest)).hexdigest()
            gate = {
                "task_id": task_id,
                "status": "PASS",
                "production_write": False,
                "tests": "PASS",
                "unexpected_changes": 0,
                "rollback_plan_ready": True,
                "manifest_sha256": manifest_sha,
                "protected_snapshot": {"crm.db": {"sha256": "c" * 64}},
            }
            gate_path = root / gate_rel
            gate_path.parent.mkdir(parents=True)
            gate_path.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
            critical = {
                "owner_approval_path": owner_rel,
                "owner_approval_sha256": hashlib.sha256(owner_path.read_bytes()).hexdigest(),
                "manifest_path": manifest_rel,
                "manifest_sha256": manifest_sha,
                "gate_a_path": gate_rel,
                "gate_a_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
                "gate_b_authorized": False,
            }
            request = self.write_request(
                root,
                task_id,
                changed_paths=changed,
                requested_min_class="CRITICAL",
                critical=critical,
            )
            CP.claim_request(request, "run-1", root=root)
            result = CP.validate_critical_nonproduction(request, "run-1", root=root)
            self.assertEqual(result["status"], "PASS_NONPRODUCTION")
            self.assertFalse(result["production_write"])


if __name__ == "__main__":
    unittest.main()
