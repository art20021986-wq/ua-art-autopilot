#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github/workflows"


class WorkflowContractTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (WORKFLOWS / name).read_text(encoding="utf-8")

    def test_orchestrator_is_exact_and_manual_only(self):
        value = self.read("uaart_orchestrator.yml")
        self.assertNotIn("\n  push:", value)
        self.assertNotIn("max(task", value.casefold())
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

    def test_class_routes_share_safety_contract(self):
        for name in ("uaart_fast.yml", "uaart_standard.yml", "uaart_critical.yml"):
            with self.subTest(name=name):
                value = self.read(name)
                self.assertNotIn("workflow_dispatch:", value)
                self.assertIn("uaart-resource-", value)
                self.assertIn("ua-art-production-writer", value)
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

    def test_acceptance_is_three_consecutive_routes(self):
        value = self.read("task107_r2_acceptance.yml")
        self.assertIn("needs: unit", value)
        self.assertIn("needs: fast_canary", value)
        self.assertIn("needs: standard_canary", value)
        self.assertIn("needs: critical_canary", value)
        self.assertIn("control_plane.py accept", value)


if __name__ == "__main__":
    unittest.main()
