#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github/workflows"
ACTIVE = {
    "uaart_autostart.yml",
    "uaart_orchestrator.yml",
    "uaart_fast.yml",
    "uaart_standard.yml",
    "uaart_critical.yml",
    "uaart_backup.yml",
    "uaart_maintenance.yml",
    "uaart_monitor.yml",
    "uaart_transaction_watchdog.yml",
}


class WorkflowContractTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (WORKFLOWS / name).read_text(encoding="utf-8")

    def test_active_workflow_set_is_exact(self):
        actual = {
            path.name
            for path in WORKFLOWS.iterdir()
            if path.suffix in {".yml", ".yaml"}
        }
        self.assertEqual(actual, ACTIVE)

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
        self.assertIn("request_sha256", value)
        self.assertIn("claim_path", value)

    def test_global_autostart_is_fresh_exact_marker_only(self):
        value = self.read("uaart_autostart.yml")
        self.assertIn("branches:\n      - main", value)
        self.assertIn("tasks/launch/AUTO-*.json", value)
        self.assertIn("git diff --name-only -z", value)
        self.assertIn("--diff-filter=A", value)
        self.assertIn('test "${#changes[@]}" -eq 1', value)
        self.assertIn('test "${#additions[@]}" -eq 1', value)
        self.assertIn("verify-mode --require AUTOMATIC", value)
        self.assertIn("Commit anti-replay ledger before execution", value)
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

    def test_nonproduction_routes_never_receive_the_real_production_secret(self):
        for name in ("uaart_fast.yml", "uaart_standard.yml"):
            with self.subTest(name=name):
                self.assertNotIn(
                    "secrets.PYTHONANYWHERE_API_TOKEN", self.read(name)
                )
        critical = self.read("uaart_critical.yml")
        self.assertIn(
            "Execute authorized CRITICAL controller without Production credential",
            critical,
        )
        self.assertIn("if: inputs.production_required != 'true'", critical)
        self.assertIn("if: inputs.production_required == 'true'", critical)
        self.assertEqual(
            len(re.findall(r"secrets\.PYTHONANYWHERE_API_TOKEN", critical)), 3
        )

    def test_production_route_has_backup_transaction_rollback_and_watchdog(self):
        value = self.read("uaart_critical.yml")
        self.assertIn("execution_contract.py backup", value)
        self.assertIn("execution_contract.py backup-receipt", value)
        self.assertIn("control_plane.py transaction-open", value)
        self.assertIn("control_plane.py transaction-close", value)
        self.assertIn("UAART_TRANSACTION_ID", value)
        self.assertIn("execution_contract.py rollback", value)
        self.assertIn("failure() || cancelled()", value)
        watchdog = self.read("uaart_transaction_watchdog.yml")
        self.assertIn("group: ua-art-production-writer", watchdog)
        self.assertIn("verify-mode --require AUTOMATIC", watchdog)
        self.assertIn("transaction_watchdog.py discover", watchdog)
        self.assertIn("execution_contract.py rollback", watchdog)
        self.assertIn("control_plane.py halt", watchdog)
        self.assertEqual(
            len(re.findall(r"secrets\.PYTHONANYWHERE_API_TOKEN", watchdog)), 1
        )

    def test_only_central_callers_inherit_repository_secrets(self):
        inheritors = {
            name
            for name in ACTIVE
            if re.search(r"(?m)^\s*secrets:\s*inherit\s*$", self.read(name))
        }
        self.assertEqual(
            inheritors, {"uaart_autostart.yml", "uaart_orchestrator.yml"}
        )

    def test_maintenance_enforces_runtime_policy_and_unit_tests(self):
        value = self.read("uaart_maintenance.yml")
        self.assertIn("control_plane.py verify-mode --require AUTOMATIC", value)
        self.assertIn("unittest discover -s automation/packages/task107_r2", value)
        self.assertNotIn("uaart_rollback.yml", value)


if __name__ == "__main__":
    unittest.main()

