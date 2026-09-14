"""Permanent gate failure tests; no Production or live-data acceptance."""
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import gate as G


def module(name, relative):
    specification = importlib.util.spec_from_file_location(name, G.ROOT / relative)
    result = importlib.util.module_from_spec(specification)
    sys.modules[name] = result
    specification.loader.exec_module(result)
    return result


O = module("protection_outbox", "cloud/task088_price_sync/outbox.py")


class GateFailureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative in G.SOURCE_ROOTS:
            (self.root / relative).mkdir(parents=True)
            (self.root / relative / "candidate.py").write_text("VALUE = 1\n")
        for relative in G.WORKFLOWS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("name: fixture only\n")

    def test_missing_mandatory_v5_tests_cannot_be_treated_as_empty_success(self):
        directory, required = G.REQUIRED_TESTS["pipeline"]
        for name in required - {"test_v5_runtime.py"}:
            (self.root / directory / name).write_text("# fixture\n")
        with self.assertRaisesRegex(G.ProtectionError, "REQUIRED_REGRESSION_MISSING"):
            G.suite_files(self.root, "pipeline")

    def test_source_drift_after_passing_suite_still_fails_gate(self):
        def execute(root, name):
            if name == "pipeline":
                (root / G.SOURCE_ROOTS[0] / "candidate.py").write_text("VALUE = 2\n")
            return {"suite": name, "status": "PASS", "tests_run": 1}
        result = G.run(self.root, execute=execute)
        self.assertEqual(result["software_status"], "FAIL")
        self.assertEqual(result["reason"], "PRICE_SOURCE_CHANGED_DURING_REGRESSION")
        self.assertFalse(result["production_authorized"])

    def test_software_pass_never_claims_live_preview_or_production_authority(self):
        result = G.run(self.root, execute=lambda root, name: {"suite": name, "status": "PASS"})
        self.assertEqual(result["software_status"], "PASS")
        self.assertEqual(result["live_preview_status"], "NOT_RUN")
        self.assertFalse(result["production_authorized"])

    def test_any_suite_failure_stops_production_admission(self):
        def fail(root, name):
            raise G.ProtectionError("PRICE_REGRESSION_NOT_100_PERCENT:" + name)
        result = G.run(self.root, execute=fail)
        self.assertEqual(result["software_status"], "FAIL")
        self.assertFalse(result["production_authorized"])

    def test_symlink_source_and_alternate_import_artifact_are_rejected(self):
        target = self.root / G.SOURCE_ROOTS[0] / "alias.py"
        target.symlink_to("candidate.py")
        with self.assertRaisesRegex(G.ProtectionError, "SOURCE_SYMLINK"):
            G.source_inventory(self.root)
        target.unlink()
        (target.parent / "hidden.pyc").write_bytes(b"fixture")
        with self.assertRaisesRegex(G.ProtectionError, "BYTECODE_ARTIFACT"):
            G.source_inventory(self.root)

    def test_canonical_forward_production_and_maintenance_require_the_gate(self):
        critical = (G.ROOT / G.WORKFLOWS[0]).read_text()
        validate = critical.split("\n  validate:", 1)[1].split("\n  prepare:", 1)[0]
        production = critical.split("\n  controller_production:", 1)[1].split("\n  controller_nonproduction:", 1)[0]
        for job in (validate, production):
            self.assertIn("- name: UA/GE PRICE PROTECTION", job)
            self.assertIn("python3 -I -B cloud/ua_ge_price_protection/gate.py", job)
            step = job.split("- name: UA/GE PRICE PROTECTION", 1)[1].split("\n      - name:", 1)[0]
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn("\n        if:", step)
            self.assertNotIn("secrets.", step)
            self.assertIn("git diff --quiet", step)
            self.assertIn("set -euo pipefail", step)
        self.assertLess(production.index("- name: UA/GE PRICE PROTECTION"),
                        production.index("- name: Execute authorized CRITICAL Production controller"))
        maintenance = (G.ROOT / G.WORKFLOWS[1]).read_text()
        self.assertIn("python3 -I -B cloud/ua_ge_price_protection/gate.py", maintenance)


class PriceIntentProtectionTests(unittest.TestCase):
    """Repeat the user-visible input contract against real outbox SQL behavior."""
    def setUp(self):
        self.database = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(self.database.close)
        self.database.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,vin TEXT,published INTEGER,price_uah INTEGER,price_georgia INTEGER,status TEXT,title TEXT,photos TEXT,extra_spec TEXT)")
        self.database.execute("INSERT INTO cars VALUES(17,'UA-0017','VIN-PROTECTED-17',1,24500,18000,'ge_waiting','Protected vehicle','[photo1,photo2]','Protected extra specification')")
        self.before = self.database.execute("SELECT * FROM cars").fetchall()
        self.schema = self.database.execute("SELECT sql FROM sqlite_master WHERE name='cars'").fetchone()
        self.database.execute("BEGIN IMMEDIATE")
        O.install(self.database)
        self.database.commit()

    def submit(self, operation, field, value):
        self.database.execute("BEGIN IMMEDIATE")
        try:
            result = O.submit(self.database, event_key=hashlib.sha256(operation.encode()).hexdigest(),
                car_id=17, field=field, value=value, actor_id=7, chat_id=7, now_ms=1000)
            self.database.commit()
            return result
        except Exception:
            self.database.rollback()
            raise

    def test_all_operator_inputs_persist_separately_without_speculative_db_changes(self):
        results = [self.submit(str(index), "price_georgia", value)
                   for index, value in enumerate((18000, 18500, 18300, 18900))]
        self.assertEqual([row["sequence"] for row in results], [1, 2, 3, 4])
        self.assertEqual([row["value"] for row in results], ["18000.00", "18500.00", "18300.00", "18900.00"])
        self.assertEqual({row["state"] for row in results}, {"QUEUED"})
        self.assertEqual(self.database.execute("SELECT * FROM cars").fetchall(), self.before)
        self.assertEqual(self.database.execute("SELECT sql FROM sqlite_master WHERE name='cars'").fetchone(), self.schema)

    def test_technical_replay_and_deliberate_same_price_have_distinct_semantics(self):
        first = self.submit("telegram-update-100", "price_uah", 24500)
        replay = self.submit("telegram-update-100", "price_uah", 24500)
        deliberate = self.submit("telegram-update-101", "price_uah", 24500)
        self.assertEqual(first, replay)
        self.assertNotEqual(first["event_key"], deliberate["event_key"])
        self.assertEqual(deliberate["sequence"], 2)

    def test_nullable_ge_intent_and_ua_intent_do_not_overwrite_each_other(self):
        ukraine = self.submit("ukraine", "price_uah", 24600)
        georgia = self.submit("georgia", "price_georgia", None)
        self.assertEqual((ukraine["field"], ukraine["value"]), ("price_uah", "24600.00"))
        self.assertEqual((georgia["field"], georgia["value"]), ("price_georgia", None))
        self.assertEqual(self.database.execute("SELECT * FROM cars").fetchall(), self.before)
        with self.assertRaisesRegex(O.OutboxError, "EARLIER_CAR_OPERATION_UNFINISHED"):
            O.require_head(self.database, georgia["event_key"])


if __name__ == "__main__":
    unittest.main()
