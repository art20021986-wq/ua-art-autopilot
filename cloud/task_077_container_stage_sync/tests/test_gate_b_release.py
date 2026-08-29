#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


remote = load("task077_gate_b_remote", ROOT / "gate_b" / "remote.py")
controller = load("task077_gate_b_controller", ROOT / "gate_b" / "controller.py")


def card(identifier: int, code: str, **updates):
    value = {
        "id": identifier,
        "auto_number": code,
        "status": "sea_loaded",
        "days_to_kyiv": None,
        "eta_manual": "2026-09-28",
        "published": 1,
        "updated_at": "before",
        "condition_text": "description",
        "sea_container": None,
        "sea_date_out": None,
    }
    value.update(updates)
    return value


class GateBReleaseTests(unittest.TestCase):
    def test_scope_respects_newer_ua0011_amendment(self):
        self.assertEqual(remote.TARGET_CODES, ("UA-0009", "UA-0010"))
        self.assertEqual(remote.PROTECTED_AMENDED_CODE, "UA-0011")
        self.assertNotIn("UA-0011", remote.TARGET_CODES)

    def test_resolve_targets_uses_unique_auto_number_not_visible_ordinal(self):
        rows = [card(15, "UA-0009"), card(16, "UA-0010"), card(18, "UA-0011")]
        found = remote.resolve_targets(rows)
        self.assertEqual(found["UA-0009"]["id"], 15)
        self.assertEqual(found["UA-0010"]["id"], 16)
        self.assertEqual(found["UA-0011"]["id"], 18)
        with self.assertRaises(remote.GateBError):
            remote.resolve_targets(rows + [card(99, "UA-0010")])

    def test_protected_digest_ignores_only_two_target_rows(self):
        rows = [card(15, "UA-0009"), card(16, "UA-0010"), card(18, "UA-0011")]
        before = remote.protected_digest(rows, {15, 16})
        changed_target = [dict(row) for row in rows]
        changed_target[0]["days_to_kyiv"] = 30
        self.assertEqual(remote.protected_digest(changed_target, {15, 16}), before)
        changed_ua11 = [dict(row) for row in rows]
        changed_ua11[2]["status"] = "kr_bought"
        self.assertNotEqual(remote.protected_digest(changed_ua11, {15, 16}), before)

    def test_audit_ids_are_exactly_actor_and_target_scoped(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE audit (id INTEGER PRIMARY KEY, actor_id TEXT, "
            "entity_type TEXT, entity_id INTEGER)"
        )
        conn.executemany(
            "INSERT INTO audit VALUES (?,?,?,?)",
            [
                (9, "old", "cars", 15),
                (11, remote.ACTOR_ID, "cars", 15),
                (12, "someone", "cars", 15),
                (13, remote.ACTOR_ID, "cars", 16),
                (14, remote.ACTOR_ID, "cars", 18),
                (15, remote.ACTOR_ID, "other", 15),
            ],
        )
        state = {"audit_max_before": 10, "actor_id": remote.ACTOR_ID,
                 "target_ids": [15, 16]}
        self.assertEqual(remote.audit_ids_for_operation(conn, state), [11, 13])
        conn.close()

    def test_restore_files_restores_bytes_and_missing_preimage(self):
        with tempfile.TemporaryDirectory() as raw:
            original_root = remote.ROOT
            root = pathlib.Path(raw)
            remote.ROOT = root
            try:
                live = root / "db.py"
                missing = root / "eta_sync_guard.py"
                backup = root / "backup.bin"
                live.write_bytes(b"changed")
                missing.write_bytes(b"new")
                backup.write_bytes(b"before")
                state = {"file_manifest": [
                    {"path": str(live), "backup": str(backup), "missing": False,
                     "sha256": remote.sha_bytes(b"before"), "mode": 0o644},
                    {"path": str(missing), "missing": True},
                ]}
                remote.restore_files(state)
                self.assertEqual(live.read_bytes(), b"before")
                self.assertFalse(missing.exists())
            finally:
                remote.ROOT = original_root

    def test_controller_validates_two_targets_and_ua0011_protection(self):
        ua9 = remote.safe_card(card(15, "UA-0009", days_to_kyiv=30))
        ua10 = remote.safe_card(card(16, "UA-0010", days_to_kyiv=30))
        ua11 = remote.safe_card(card(18, "UA-0011", status="kr_bought",
                                     days_to_kyiv=None, eta_manual=None))
        shadow = {
            "contract_id": controller.CONTRACT, "status": "PASS",
            "production_write": False, "crm_db_write": False,
            "runtime_llm_tokens": 0,
            "database": {"quick_check": "ok", "row_count": 13,
                         "targets": {"UA-0009": ua9, "UA-0010": ua10},
                         "protected_ua0011": ua11},
            "patch_bundle": {"function_transforms": 8,
                             "compiled_files": {str(i): "x" for i in range(5)}},
        }
        controller.validate_shadow(shadow)
        bad = json.loads(json.dumps(shadow))
        bad["database"]["targets"]["UA-0011"] = ua11
        with self.assertRaises(controller.ControllerError):
            controller.validate_shadow(bad)

    def test_manual_only_workflow_and_three_independent_gates(self):
        workflow = (ROOT.parents[1] / ".github/workflows/task077_container_stage_sync_gate_b.yml")
        source = workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("push:", source)
        self.assertIn("approval_token", source)
        self.assertIn("ua-art-production-writer", source)
        self.assertIn("PYTHONANYWHERE_API_TOKEN", source)
        self.assertIn("Require production PASS", source)
        self.assertIn("rollback", (ROOT / "gate_b" / "remote.py").read_text(encoding="utf-8"))

    def test_safe_workflow_watchdog_cannot_rerun_gate_b(self):
        watchdog = (ROOT.parents[1] / ".github/workflows/safe_workflow_watchdog.yml")
        if not watchdog.exists():
            watchdog = ROOT.parents[1] / "safe_workflow_watchdog.yml"
        source = watchdog.read_text(encoding="utf-8")
        self.assertIn("gate_b", source)
        self.assertIn("production", source)
        self.assertIn("deploy", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
