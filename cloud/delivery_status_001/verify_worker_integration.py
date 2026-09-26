"""Check the delivery branch of the existing worker with a temporary SQLite DB."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import delivery_status as policy
from integration_patch import SOURCE_SHA256, patch_public_sync
from verify_catalog_integration import load_module


class WorkerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.publish = Mock(return_value=(True, "ok"))
        self.verify = Mock()
        self.hide = Mock(return_value={"status": "APPLIED"})
        self.modules = patch.dict(sys.modules, {
            "ua_delivery_status": policy,
            "ua_stage_catalog_sync": SimpleNamespace(reconcile=self.hide),
            "ua_public_freshness": SimpleNamespace(verify_public=self.verify),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        name = "ua_crm_public_sync.py"
        raw = (Path(os.environ.get("DELIVERY_SOURCE_ROOT", "/home/Carix")) / name).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA256[name])
        candidate = self.root / name
        candidate.write_text(patch_public_sync(raw.decode()), encoding="utf-8")
        self.worker = load_module(candidate)
        self.worker.ROOT = self.root
        self.worker.STATE = self.root / "state.json"
        self.worker.LOCK = self.root / "worker.lock"
        with sqlite3.connect(self.root / "crm.db") as conn:
            conn.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, status TEXT, published INTEGER)")
            conn.execute("INSERT INTO cars VALUES(1, 'UA-0001', 'kr_bought', 1)")
        self.worker.STATE.write_text(json.dumps({"version": 1, "revisions": self.worker.snapshot()}))

    def change_status(self, value):
        with sqlite3.connect(self.root / "crm.db") as conn:
            conn.execute("UPDATE cars SET status=? WHERE id=1", (value,))

    def run_once(self):
        return self.worker.reconcile_once(publish=self.publish, clock=lambda: 100)

    def test_old_ledger_does_not_republish_unchanged_cars(self):
        state = json.loads(self.worker.STATE.read_text())
        state["revisions"]["1"].pop("delivery_status")
        self.worker.STATE.write_text(json.dumps(state))
        self.assertEqual(self.run_once(), "idle")
        self.publish.assert_not_called()
        self.hide.assert_not_called()

    def test_hidden_removes_from_catalog_and_finishes_revision(self):
        self.change_status("hidden")
        self.assertEqual(self.run_once(), "hidden")
        self.hide.assert_called_once_with(apply=True)
        self.publish.assert_not_called()
        self.verify.assert_not_called()
        state = json.loads(self.worker.STATE.read_text())
        self.assertEqual(state["retry"], {})
        self.assertEqual(state["revisions"], self.worker.snapshot())
        self.assertEqual(self.run_once(), "idle")

    def test_unknown_status_also_hides_without_publication(self):
        self.change_status("sea_unknown")
        self.assertEqual(self.run_once(), "hidden")
        self.publish.assert_not_called()
        self.hide.assert_called_once_with(apply=True)

    def test_reactivation_uses_existing_full_publisher(self):
        self.change_status("hidden")
        self.assertEqual(self.run_once(), "hidden")
        self.change_status("ferry")
        self.assertEqual(self.run_once(), "published")
        self.publish.assert_called_once_with("UA-0001")
        self.verify.assert_called_once_with("UA-0001")

    def test_concurrent_edit_does_not_advance_ledger(self):
        initial = json.loads(self.worker.STATE.read_text())["revisions"]
        self.change_status("hidden")
        self.hide.side_effect = lambda **_: self.change_status("kyiv")
        self.assertEqual(self.run_once(), "changed_during_publish")
        self.assertEqual(json.loads(self.worker.STATE.read_text())["revisions"], initial)

    def test_operational_failure_retains_retry_and_old_revision(self):
        initial = json.loads(self.worker.STATE.read_text())["revisions"]
        self.change_status("hidden")
        self.hide.side_effect = OSError("test write failure")
        with self.assertLogs(self.worker.LOG, level="ERROR"):
            self.assertEqual(self.run_once(), "idle")
        state = json.loads(self.worker.STATE.read_text())
        self.assertEqual(state["revisions"], initial)
        self.assertEqual(state["retry"]["1"]["count"], 1)
        self.publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
