"""Public fence regressions using the actual inserted helper and local SQLite."""
import contextlib
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import gate as G


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, G.ROOT / "cloud/task088_price_sync" / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


O = load("price_protection_guard_outbox", "outbox.py")
P = load("price_protection_guard_patch", "patch_guard.py")


class PublishError(RuntimeError):
    pass


class PublicFenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "crm.sqlite"
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=0)
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,published INTEGER,price_uah INTEGER,price_georgia INTEGER,vin TEXT)")
        self.db.execute("INSERT INTO cars VALUES(19,'UA-0019',1,24500,NULL,'PROTECTED-VIN')")
        self.db.execute("BEGIN IMMEDIATE")
        O.install(self.db)
        self.db.commit()
        self.before = self.db.execute("SELECT * FROM cars").fetchall()
        namespace = {"contextlib": contextlib, "sqlite3": sqlite3, "DB": self.path, "PublishError": PublishError}
        exec(compile(P.HELPER, "<actual-public-price-fence-helper>", "exec"), namespace)
        self.fence = namespace["_task088_price_quiescence"]
        self.modules = patch.dict(sys.modules, {"uaart_price_sync_outbox": O})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_pending_v5_operator_intent_blocks_full_generation_without_mutating_rows(self):
        self.db.execute("BEGIN IMMEDIATE")
        O.submit(self.db, event_key=hashlib.sha256(b"deliberate input").hexdigest(), car_id=19,
                 field="price_georgia", value=18900, actor_id=7, chat_id=7, now_ms=1000)
        self.db.commit()
        with self.assertRaisesRegex(PublishError, "V5_UNVERIFIED_PRICE_INTENTS"):
            with self.fence():
                self.fail("Unverified queued value admitted to full generation")
        self.assertEqual(self.db.execute("SELECT * FROM cars").fetchall(), self.before)

    def test_pending_legacy_intent_remains_fenced(self):
        self.db.execute("BEGIN IMMEDIATE")
        O.enqueue(self.db, event_key=hashlib.sha256(b"legacy input").hexdigest(), car_id=19,
                  ukraine_usd="24500.00", georgia_usd=None, now_ms=1000)
        self.db.commit()
        with self.assertRaisesRegex(PublishError, "UNVERIFIED_PRICE_INTENTS"):
            with self.fence():
                self.fail("Legacy unresolved publication admitted")

    def test_guard_holds_writer_exclusion_and_releases_it_without_data_changes(self):
        with self.fence():
            with self.assertRaises(sqlite3.OperationalError):
                self.db.execute("UPDATE cars SET price_uah=24600 WHERE id=19")
            self.assertEqual(self.db.execute("SELECT * FROM cars").fetchall(), self.before)
        self.db.execute("BEGIN IMMEDIATE")
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT * FROM cars").fetchall(), self.before)

    def test_missing_v5_permanent_audit_trigger_refuses_full_publication(self):
        self.db.execute("DROP TRIGGER " + O.V5_AUDIT + "_no_delete")
        with self.assertRaisesRegex(PublishError, "PROTECTION_TRIGGER_REQUIRED"):
            with self.fence():
                self.fail("Missing permanent price audit protection admitted")


if __name__ == "__main__":
    unittest.main()
