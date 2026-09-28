from __future__ import annotations

import copy
import unittest

from automation.packages.task116.contracts import ContractError, validate_record, validate_transition
from automation.packages.task116.metrics import calculate_readiness, useful_run_metrics
from automation.packages.task116.reconcile import reconcile_snapshot


def record(**changes):
    value = {
        "task_id": "TASK116-AUTOPILOT-MAX-RELIABILITY",
        "request_sha256": "a" * 64,
        "state": "RECEIVED",
        "production_required": False,
        "production_allowed": False,
        "gate_b_pass": False,
        "owner_approved": True,
        "backup_ready": False,
        "resources": ["CONTROL_PLANE:TASK116"],
    }
    value.update(changes)
    return value


def empty_snapshot():
    return {
        "registry": [],
        "requests": [],
        "branches": [],
        "pull_requests": [],
        "claims": [],
        "runs": [],
        "transactions": [],
        "receipts": [],
    }


class ContractTests(unittest.TestCase):
    def test_valid_sandbox_record(self):
        self.assertEqual(validate_record(record())["state"], "RECEIVED")

    def test_invalid_task_id_rejected(self):
        with self.assertRaises(ContractError):
            validate_record(record(task_id="../TASK116"))

    def test_duplicate_resources_rejected(self):
        with self.assertRaises(ContractError):
            validate_record(record(resources=["A", "A"]))

    def test_production_without_gates_rejected(self):
        with self.assertRaises(ContractError):
            validate_record(record(production_required=True, production_allowed=True))

    def test_production_with_all_gates_allowed(self):
        result = validate_record(
            record(
                production_required=True,
                production_allowed=True,
                gate_b_pass=True,
                owner_approved=True,
                backup_ready=True,
            )
        )
        self.assertTrue(result["production_allowed"])

    def test_legal_transition(self):
        validate_transition(record(), record(state="PLANNING"))

    def test_illegal_transition(self):
        with self.assertRaises(ContractError):
            validate_transition(record(), record(state="FINISHED"))

    def test_identity_drift_rejected(self):
        with self.assertRaises(ContractError):
            validate_transition(record(), record(state="PLANNING", request_sha256="b" * 64))


class MetricTests(unittest.TestCase):
    def test_noop_jobs_are_excluded(self):
        result = useful_run_metrics(
            [
                {"task_id": "TASK001", "kind": "watchdog_noop", "attempt": 1, "conclusion": "success"},
                {"task_id": "TASK002", "kind": "task", "attempt": 1, "conclusion": "failure"},
                {"task_id": "TASK002", "kind": "task", "attempt": 2, "conclusion": "success"},
            ]
        )
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["attempt_success_percent"], 50.0)
        self.assertEqual(result["first_attempt_success_percent"], 0.0)

    def test_readiness_matches_audit_formula(self):
        result = calculate_readiness(
            {
                "owner_request_autonomy": 42,
                "guarded_orchestration": 79,
                "production_reliability": 55,
                "live_result_quality": 75,
                "observability": 40,
            },
            {
                "main_protected": False,
                "rollback_5_of_5": False,
                "first_attempt_95": False,
                "status_fresh_5m": False,
                "vin_no_ads": True,
                "specification_complete": True,
                "soak_72h": False,
                "unexpected_changes_zero": True,
            },
        )
        self.assertEqual(result["raw_score"], 58.95)
        self.assertEqual(result["effective_score"], 58.95)
        self.assertEqual(result["status"], "NOT_ACCEPTED")

    def test_score_is_capped_without_main_protection(self):
        gates = {key: True for key in (
            "main_protected", "rollback_5_of_5", "first_attempt_95", "status_fresh_5m",
            "vin_no_ads", "specification_complete", "soak_72h", "unexpected_changes_zero"
        )}
        gates["main_protected"] = False
        result = calculate_readiness({key: 100 for key in (
            "owner_request_autonomy", "guarded_orchestration", "production_reliability",
            "live_result_quality", "observability"
        )}, gates)
        self.assertEqual(result["effective_score"], 79.0)


class ReconciliationTests(unittest.TestCase):
    def test_empty_snapshot_passes(self):
        self.assertEqual(reconcile_snapshot(empty_snapshot())["status"], "PASS")

    def test_out_of_queue_task_is_detected(self):
        snapshot = empty_snapshot()
        snapshot["branches"].append({"task_id": "TASK112-GE-8-COUNTRY"})
        result = reconcile_snapshot(snapshot)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["findings"]["lost_tasks"], ["TASK112-GE-8-COUNTRY"])

    def test_finished_without_receipt_is_rejected(self):
        snapshot = empty_snapshot()
        snapshot["registry"].append({"task_id": "TASK108-CARD-REPAIR", "state": "FINISHED"})
        snapshot["requests"].append({"task_id": "TASK108-CARD-REPAIR"})
        result = reconcile_snapshot(snapshot)
        self.assertEqual(result["findings"]["false_finished"], ["TASK108-CARD-REPAIR"])

    def test_duplicate_request_is_detected(self):
        snapshot = empty_snapshot()
        task = {"task_id": "TASK116-AUTOPILOT-MAX-RELIABILITY"}
        snapshot["registry"].append({**task, "state": "BLOCKED"})
        snapshot["requests"] = [copy.deepcopy(task), copy.deepcopy(task)]
        result = reconcile_snapshot(snapshot)
        self.assertEqual(result["findings"]["duplicates"]["requests"], [task["task_id"]])


if __name__ == "__main__":
    unittest.main()
