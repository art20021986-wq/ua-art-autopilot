#!/usr/bin/env python3
import json
import decimal
import pathlib
import sqlite3
import tempfile
import types
import unittest
from unittest import mock

import owner_preflight as probe


class OwnerPreflightTests(unittest.TestCase):
    def test_displayed_quota_units_cannot_overstate_capacity(self):
        for text, byte_limit in (("35 GB", 35000000000), ("35 GiB", 37580963840)):
            actual = decimal.Decimal(probe.quota_input_gib(text)) * 1024 ** 3
            self.assertEqual(actual, byte_limit)
        for ambiguous in ("35", "35 MB", "35 GB plus extra"):
            with self.assertRaises(probe.ProbeError):
                probe.quota_input_gib(ambiguous)

    def test_source_inventory_omits_credentials_and_live_values(self):
        source = '''TOKEN = "123456:secret-do-not-export"
LIVE_VALUE = "John Smith 555-1020"
EDITABLE = [("price_uah", "Цена продажи")]
def apply_value(card_id, field, raw, actor_id):
    token = "another-private-secret"
    contact = "555-0000"
    return remote("secret-request", token)
def register(app):
    app.add_handler(CallbackQueryHandler(secret, pattern="private-pattern"), group=7)
'''
        encoded = json.dumps(probe.source_shape(source.encode(), "cars_ui.py"))
        for secret in ("secret-do-not-export", "John Smith", "another-private-secret", "555-0000", "private-pattern", "secret-request"):
            self.assertNotIn(secret, encoded)
        self.assertIn('"group": 7', encoded)
        self.assertIn("apply_value", encoded)

    def test_database_read_only_includes_wal_committed_schema(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            writer = sqlite3.connect(root / "crm.db")
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY, published INTEGER, price_uah INTEGER)")
            writer.execute("INSERT INTO cars VALUES(7, 0, 43210987)")
            writer.commit()
            writer.execute("ALTER TABLE cars ADD COLUMN price_georgia INTEGER")
            writer.commit()
            before = list(writer.execute("SELECT * FROM cars"))
            result = probe.database_probe(root)
            self.assertIn("price_georgia", {item["name"] for item in result["columns"]})
            self.assertEqual(result["unpublished_candidate_ids"], [7])
            self.assertNotIn("43210987", json.dumps(result))
            self.assertEqual(list(writer.execute("SELECT * FROM cars")), before)
            writer.close()

    def test_wal_database_without_shm_refuses_before_connect(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            with sqlite3.connect(root / "crm.db") as writer:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("CREATE TABLE cars(id INTEGER)")
            writer.close()
            self.assertFalse((root / "crm.db-shm").exists())
            with mock.patch.object(probe.sqlite3, "connect") as connect:
                with self.assertRaises(probe.ProbeError):
                    probe.database_probe(root)
                connect.assert_not_called()

    def test_missing_nfs_quota_never_uses_global_capacity_for_gate(self):
        quota = types.SimpleNamespace(target_mount=lambda: {}, nfs_rquota_probe=lambda mount: {"status": "unavailable"})
        with tempfile.TemporaryDirectory() as raw:
            result = probe.storage_probe(pathlib.Path(raw), quota)
        self.assertFalse(result["gate_eligible"])
        self.assertNotIn("total_bytes", result)
        self.assertIn("diagnostic_global_volume_only", result)

    def test_hard_quota_uses_account_values(self):
        quota = types.SimpleNamespace(target_mount=lambda: {}, nfs_rquota_probe=lambda mount: {"status": "PASS", "active": True, "block_hard_limit": 100, "total_bytes": 10000, "used_bytes": 3000, "free_bytes": 7000})
        result = probe.storage_probe(pathlib.Path("/tmp"), quota)
        self.assertTrue(result["gate_eligible"])
        self.assertEqual(result["total_bytes"], 10000)

    def test_owner_current_quota_requires_complete_successful_usage(self):
        completed = types.SimpleNamespace(returncode=0, stdout="10\t/tmp\n20\t/home/Carix\n30\t/var/www\n")
        with mock.patch.object(probe.subprocess, "run", return_value=completed) as run:
            result = probe.owner_quota_capacity(pathlib.Path("/home/Carix"), "35.0")
        self.assertEqual(result["used_bytes"], 60)
        self.assertEqual(result["total_bytes"], 35 * 1024 ** 3)
        self.assertNotIn("shell", run.call_args.kwargs)
        completed.returncode = 1
        with mock.patch.object(probe.subprocess, "run", return_value=completed):
            with self.assertRaises(probe.ProbeError):
                probe.owner_quota_capacity(pathlib.Path("/home/Carix"), "35")

    def test_partial_probe_omits_exception_text_and_never_claims_runtime(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            for name in probe.SOURCES:
                (root / name).write_text("def placeholder():\n    return 1\n")
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            with mock.patch.object(probe.ui_patch, "patch_text", side_effect=RuntimeError("secret-exception-text")), mock.patch.object(probe, "storage_probe", return_value={"status": "NOT_VERIFIED", "gate_eligible": False}):
                result = probe.collect(root)
            self.assertNotIn("secret-exception-text", json.dumps(result))
            self.assertFalse(result["candidate"]["live_bot_verified"])
            self.assertEqual(result["source_consistency"], "PASS")
            self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
