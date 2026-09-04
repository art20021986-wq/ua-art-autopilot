#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github/workflows"


class WorkflowContractTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (WORKFLOWS / name).read_text(encoding="utf-8")

    def test_orchestrator_is_exact_and_mode_validated(self):
        value = self.read("uaart_orchestrator.yml")
        self.assertNotIn("\n  push:", value)
        self.assertNotIn("max(task", value.casefold())
        self.assertIn("control_plane.py verify-mode", value)
        self.assertIn("expected_request_sha256", value)
        self.assertIn("--expected-sha256", value)
        self.assertIn("autostart_ledger_path", value)
        self.assertIn("--autostart-ledger", value)
        self.assertIn("autostart_source_commit", value)
        self.assertIn("--autostart-source-commit", value)
        self.assertIn("control_plane.py claim", value)
        self.assertIn("verify-request", value)
        self.assertIn("planning", value)
        self.assertIn("request_sha256", value)
        self.assertIn("claim_path", value)

    def test_autostart_guard_accepts_only_exact_identity(self):
        value = self.read("autopilot_autostart_guard.yml")
        self.assertNotIn("\n  push:", value)
        self.assertNotIn("\n  schedule:", value)
        self.assertIn("verify-identity", value)
        self.assertIn("task_sha256", value)
        self.assertIn("run_id", value)
        self.assertIn("GENERIC_RECENT_RUN_ACCEPTED=NO", value)

    def test_global_autostart_is_fresh_exact_marker_only(self):
        value = self.read("uaart_autostart.yml")
        self.assertIn("branches:\n      - main", value)
        self.assertIn("tasks/launch/AUTO-*.json", value)
        self.assertIn("git diff --name-only -z", value)
        self.assertIn("--diff-filter=A", value)
        self.assertIn("test \"${#changes[@]}\" -eq 1", value)
        self.assertIn("test \"${#additions[@]}\" -eq 1", value)
        self.assertIn("test \"${changes[0]}\" = \"${additions[0]}\"", value)
        self.assertIn("verify-mode --require AUTOMATIC", value)
        self.assertIn("autostart_intake.py", value)
        self.assertIn("Commit anti-replay ledger before execution", value)
        self.assertIn("expected_request_sha256", value)
        self.assertIn("autostart_ledger_path", value)
        self.assertIn("autostart_source_commit", value)
        self.assertIn("uses: ./.github/workflows/uaart_orchestrator.yml", value)

    def test_class_routes_share_safety_contract(self):
        for name in ("uaart_fast.yml", "uaart_standard.yml", "uaart_critical.yml"):
            with self.subTest(name=name):
                value = self.read(name)
                self.assertNotIn("workflow_dispatch:", value)
                self.assertIn("uaart-resource-", value)
                self.assertIn("ua-art-production-writer", value)
                self.assertIn("control_plane.py verify-mode", value)
                self.assertIn("verify-identity", value)
                self.assertIn("control_plane.py storage", value)
                self.assertGreaterEqual(value.count("control_plane.py health"), 2)
                self.assertIn("control_plane.py finish", value)
                self.assertIn("Persist fail-closed state", value)

    def test_critical_nonproduction_is_not_forced_through_gate_b(self):
        value = self.read("uaart_critical.yml")
        self.assertIn("critical-nonprod", value)
        self.assertIn("critical-production", value)
        self.assertIn("inputs.production_required != 'true'", value)
        self.assertIn("inputs.production_required == 'true'", value)

    def test_production_route_has_backup_transaction_rollback_and_watchdog(self):
        value = self.read("uaart_critical.yml")
        self.assertIn("execution_contract.py backup", value)
        self.assertIn("execution_contract.py backup-receipt", value)
        self.assertIn("control_plane.py transaction-open", value)
        self.assertIn("control_plane.py transaction-close", value)
        self.assertIn("UAART_TRANSACTION_ID", value)
        self.assertIn("UAART_BACKUP_MANIFEST_SHA256", value)
        self.assertIn("execution_contract.py rollback", value)
        self.assertIn("execution_contract.py rollback-receipt", value)
        self.assertIn("failure() || cancelled()", value)
        watchdog = self.read("uaart_transaction_watchdog.yml")
        self.assertIn("group: ua-art-production-writer", watchdog)
        self.assertIn("transaction_watchdog.py discover", watchdog)
        self.assertIn("execution_contract.py rollback", watchdog)
        self.assertIn("control_plane.py halt", watchdog)

    def test_known_legacy_production_chains_are_manual_only(self):
        names = (
            "overnight_autopilot_production_dispatch.yml",
            "overnight_task099_transient_recovery.yml",
            "task059_ai_fast_schema.yml",
            "pythonanywhere_sync.yml",
            "owner_ua0011_korea_now_production.yml",
        )
        for name in names:
            with self.subTest(name=name):
                value = self.read(name)
                trigger = value.split("permissions:", 1)[0]
                self.assertIn("workflow_dispatch:", trigger)
                self.assertNotIn("workflow_run:", trigger)
                self.assertNotIn("\n  push:", trigger)
                self.assertNotIn("\n  schedule:", trigger)

    def test_explicit_rollback_queue_is_task_scoped(self):
        value = self.read("uaart_rollback.yml")
        self.assertNotIn("--task 105", value)
        self.assertIn("os.environ['TASK_ID']", value)
        self.assertIn('--task "$ticket"', value)

    def test_acceptance_is_three_consecutive_routes(self):
        value = self.read("task107_r2_acceptance.yml")
        self.assertIn("needs: unit", value)
        self.assertIn("needs: fast_canary", value)
        self.assertIn("needs: standard_canary", value)
        self.assertIn("needs: critical_canary", value)
        self.assertIn("control_plane.py accept", value)


if __name__ == "__main__":
    unittest.main()
