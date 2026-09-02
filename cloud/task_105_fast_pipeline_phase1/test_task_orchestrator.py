from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.task_orchestrator import (
    AIRoute,
    FailureClass,
    OrchestratorError,
    TaskClass,
    TaskRequest,
    TaskStatus,
    build_plan,
    classify_failure,
    decide_retry,
    locks_conflict,
    validate_receipt,
    validate_transition,
)


class ClassificationTests(unittest.TestCase):
    def test_fast_exact_text_change_uses_no_ai(self) -> None:
        request = TaskRequest.from_mapping({
            "task_id": "FAST-001",
            "title": "Replace exact contact label",
            "description": "replace exact text, validate link and HTTP 200",
            "changed_paths": ["public/contact.html"],
            "production_required": True,
            "complexity": 1,
        })
        plan = build_plan(request)
        self.assertEqual(plan.task_class, TaskClass.FAST)
        self.assertEqual(plan.ai_route, AIRoute.NO_AI)
        self.assertEqual(plan.ai_call_budget, 0)
        self.assertEqual(plan.retry_budget, 2)
        self.assertEqual(plan.resource_locks, ("CONTENT_SURFACE",))

    def test_standard_crm_logic(self) -> None:
        request = TaskRequest.from_mapping({
            "task_id": "STD-001",
            "title": "Fix CRM stage counter",
            "description": "correct stage counter and publication logic",
            "changed_paths": ["src/crm/counters.py"],
            "production_required": True,
            "complexity": 3,
        })
        plan = build_plan(request)
        self.assertEqual(plan.task_class, TaskClass.STANDARD)
        self.assertIn("CRM_DB", plan.resource_locks)
        self.assertEqual(plan.ai_route, AIRoute.GPT_PRIMARY)

    def test_protected_workflow_path_is_critical(self) -> None:
        request = TaskRequest.from_mapping({
            "task_id": "CRIT-001",
            "title": "Edit deployment",
            "description": "change workflow",
            "changed_paths": [".github/workflows/release.yml"],
            "production_required": True,
        })
        plan = build_plan(request)
        self.assertEqual(plan.task_class, TaskClass.CRITICAL)
        self.assertIn("CONTROL_PLANE", plan.resource_locks)

    def test_database_is_critical(self) -> None:
        request = TaskRequest.from_mapping({
            "task_id": "CRIT-DB",
            "title": "Update CRM schema",
            "description": "database migration",
            "changed_paths": ["runtime/crm.db"],
            "production_required": True,
        })
        self.assertEqual(build_plan(request).task_class, TaskClass.CRITICAL)

    def test_read_only_does_not_downgrade_protected_scope(self) -> None:
        request = TaskRequest.from_mapping({
            "task_id": "CRIT-RO",
            "title": "Audit release workflow",
            "description": "read only",
            "changed_paths": [".github/workflows/release.yml"],
            "read_only": True,
        })
        plan = build_plan(request)
        self.assertEqual(plan.task_class, TaskClass.CRITICAL)
        self.assertEqual(plan.resource_locks, ())

    def test_owner_minimum_only_escalates(self) -> None:
        request = TaskRequest.from_mapping({
            "task_id": "ESC-001",
            "title": "Change label",
            "description": "exact replace",
            "changed_paths": ["public/a.html"],
            "requested_min_class": "STANDARD",
        })
        self.assertEqual(build_plan(request).task_class, TaskClass.STANDARD)

    def test_unsafe_path_rejected(self) -> None:
        with self.assertRaises(OrchestratorError):
            TaskRequest.from_mapping({
                "task_id": "BAD-001",
                "title": "bad",
                "changed_paths": ["../secret"],
            })

    def test_complexity_range_rejected(self) -> None:
        with self.assertRaises(OrchestratorError):
            TaskRequest.from_mapping({
                "task_id": "BAD-002",
                "title": "bad",
                "complexity": 9,
            })


class ResourceLockTests(unittest.TestCase):
    def test_different_cards_do_not_conflict(self) -> None:
        self.assertFalse(locks_conflict(("CARD:UA-0001",), ("CARD:UA-0002",)))

    def test_same_resource_conflicts(self) -> None:
        self.assertTrue(locks_conflict(("CRM_DB",), ("CRM_DB",)))

    def test_global_conflicts_with_any_writer(self) -> None:
        self.assertTrue(locks_conflict(("GLOBAL_PRODUCTION",), ("HOMEPAGE",)))

    def test_all_cards_conflicts_with_one_card(self) -> None:
        self.assertTrue(locks_conflict(("CATALOG_ALL_CARDS",), ("CARD:UA-0016",)))

    def test_read_only_empty_locks_do_not_conflict(self) -> None:
        self.assertFalse(locks_conflict((), ("CRM_DB",)))


class RetryPolicyTests(unittest.TestCase):
    def test_429_is_transient(self) -> None:
        self.assertEqual(classify_failure("HTTP 429 rate limit"), FailureClass.TRANSIENT)

    def test_503_is_transient(self) -> None:
        decision = decide_retry(TaskClass.FAST, "HTTP 503 temporary", 0)
        self.assertTrue(decision.retry_allowed)
        self.assertEqual(decision.action, "RETRY_SAME_TASK_ID")

    def test_retry_budget_exhaustion(self) -> None:
        decision = decide_retry(TaskClass.FAST, "timeout", 2)
        self.assertFalse(decision.retry_allowed)
        self.assertEqual(decision.action, "BLOCKED_CLASSIFY_ROOT_CAUSE")

    def test_syntax_error_is_not_retried(self) -> None:
        decision = decide_retry(TaskClass.STANDARD, "SyntaxError line 10", 0)
        self.assertFalse(decision.retry_allowed)
        self.assertEqual(decision.action, "BLOCKED_ROOT_CAUSE_REQUIRED")

    def test_second_same_logical_error_enters_root_cause(self) -> None:
        decision = decide_retry(
            TaskClass.STANDARD,
            "Assertion failed",
            attempts_already_used=0,
            repeated_same_signature=2,
        )
        self.assertEqual(decision.action, "ROOT_CAUSE_MODE")

    def test_protected_mutation_stops_and_rolls_back(self) -> None:
        decision = decide_retry(TaskClass.CRITICAL, "protected-file mutation", 0)
        self.assertEqual(decision.failure_class, FailureClass.SAFETY)
        self.assertEqual(decision.action, "STOP_AND_ROLLBACK")

    def test_owner_dependency_blocks(self) -> None:
        decision = decide_retry(TaskClass.CRITICAL, "owner approval required", 0)
        self.assertEqual(decision.action, "BLOCKED_WAITING_OWNER")


class StateMachineTests(unittest.TestCase):
    def test_happy_path(self) -> None:
        path = [
            TaskStatus.QUEUED,
            TaskStatus.CLASSIFYING,
            TaskStatus.RUNNING,
            TaskStatus.TESTING,
            TaskStatus.READY_FOR_DEPLOY,
            TaskStatus.DEPLOYING,
            TaskStatus.VERIFYING,
            TaskStatus.FINISHED,
        ]
        for current, target in zip(path, path[1:]):
            validate_transition(current, target)

    def test_false_finished_rejected(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_transition(TaskStatus.QUEUED, TaskStatus.FINISHED)

    def test_terminal_finished_has_no_exit(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_transition(TaskStatus.FINISHED, TaskStatus.RUNNING)

    def test_deploy_failure_can_roll_back(self) -> None:
        validate_transition(TaskStatus.DEPLOYING, TaskStatus.ROLLED_BACK)


class ReceiptTests(unittest.TestCase):
    def test_sandbox_finished_receipt(self) -> None:
        result = validate_receipt({
            "task_id": "T1",
            "status": "FINISHED",
            "task_class": "FAST",
            "target_environment": "sandbox",
            "tests": "PASS",
            "unexpected_changes": 0,
            "rollback_ready": True,
            "production_required": False,
        })
        self.assertEqual(result["status"], "FINISHED")

    def test_production_receipt_requires_live_verify(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_receipt({
                "task_id": "T2",
                "status": "FINISHED",
                "task_class": "STANDARD",
                "target_environment": "production",
                "tests": "PASS",
                "unexpected_changes": 0,
                "rollback_ready": True,
                "production_required": True,
                "backup": "/backup/T2",
                "production": "PASS",
            })

    def test_production_receipt_passes_complete_evidence(self) -> None:
        validate_receipt({
            "task_id": "T3",
            "status": "FINISHED",
            "task_class": "STANDARD",
            "target_environment": "production",
            "tests": "PASS",
            "unexpected_changes": 0,
            "rollback_ready": True,
            "production_required": True,
            "backup": "/backup/T3",
            "production": "PASS",
            "live_verify": "PASS",
        })

    def test_unexpected_changes_rejected(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_receipt({
                "task_id": "T4",
                "status": "FINISHED",
                "task_class": "FAST",
                "target_environment": "sandbox",
                "tests": "PASS",
                "unexpected_changes": 1,
                "rollback_ready": True,
                "production_required": False,
            })

    def test_false_pass_status_rejected(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_receipt({
                "task_id": "T5",
                "status": "PASS",
                "task_class": "FAST",
                "target_environment": "sandbox",
                "tests": "PASS",
                "unexpected_changes": 0,
                "rollback_ready": True,
                "production_required": False,
            })


class FailureInjectionMatrix(unittest.TestCase):
    """Required ten-scenario Phase 1 failure-injection acceptance."""

    def test_01_runner_cancelled(self) -> None:
        self.assertEqual(classify_failure("runner cancelled"), FailureClass.TRANSIENT)

    def test_02_network_timeout(self) -> None:
        self.assertEqual(classify_failure("network timeout"), FailureClass.TRANSIENT)

    def test_03_http_429(self) -> None:
        self.assertEqual(classify_failure("HTTP 429"), FailureClass.TRANSIENT)

    def test_04_pythonanywhere_502(self) -> None:
        self.assertEqual(classify_failure("PythonAnywhere HTTP 502"), FailureClass.TRANSIENT)

    def test_05_syntax_error(self) -> None:
        self.assertEqual(classify_failure("SyntaxError"), FailureClass.LOGICAL)

    def test_06_unit_regression(self) -> None:
        self.assertEqual(classify_failure("unit test regression"), FailureClass.LOGICAL)

    def test_07_protected_file_mutation(self) -> None:
        self.assertEqual(classify_failure("protected file mutation"), FailureClass.SAFETY)

    def test_08_duplicate_dispatch_uses_same_lock(self) -> None:
        self.assertTrue(locks_conflict(("CONTROL_PLANE",), ("CONTROL_PLANE",)))

    def test_09_unrelated_resources_parallel(self) -> None:
        self.assertFalse(locks_conflict(("HOMEPAGE",), ("CRM_DB",)))

    def test_10_rollback_failure_is_safety(self) -> None:
        self.assertEqual(classify_failure("rollback failure"), FailureClass.SAFETY)


if __name__ == "__main__":
    unittest.main()
