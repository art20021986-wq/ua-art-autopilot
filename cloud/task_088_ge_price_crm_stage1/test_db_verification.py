from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("task088_db_verification", HERE / "db_verification.py")
dbv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dbv)


class TestCommittedPriceProof(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = pathlib.Path(self.temporary.name) / "crm.db"
        self.keepalive = sqlite3.connect(self.path)
        self.addCleanup(self.keepalive.close)
        self.keepalive.execute("PRAGMA journal_mode=WAL")
        self.keepalive.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY, published INTEGER, "
                               "price_uah INTEGER, price_georgia INTEGER, model TEXT)")
        self.keepalive.executemany("INSERT INTO cars VALUES (?,?,?,?,?)",
                                  [(1, 1, 50000, 12345, "published"), (7, 0, 20000, None, "test")])
        self.keepalive.commit()

    def row(self, car_id=7):
        with sqlite3.connect(self.path) as conn:
            return conn.execute("SELECT * FROM cars WHERE id=?", (car_id,)).fetchone()

    def trigger(self, field, changed):
        self.keepalive.execute("CREATE TRIGGER crosswrite AFTER UPDATE OF " + field + " ON cars "
                               "BEGIN UPDATE cars SET " + changed + " WHERE id=NEW.id; END")
        self.keepalive.commit()

    def test_both_directions_are_committed_and_read_on_fresh_connections(self):
        before = self.row()
        observed, statements, connections = [], [], []
        real_connect, real_read = dbv._connect, dbv._read_fresh

        def connect(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            conn.set_trace_callback(statements.append)
            connections.append(conn)
            return conn

        def read(*args):
            value = real_read(*args)
            observed.append((value["price_uah"], value["price_georgia"]))
            return value

        # A separate WAL reader keeps its original snapshot throughout the proof.
        reader = sqlite3.connect(self.path)
        self.addCleanup(reader.close)
        reader.execute("BEGIN")
        self.assertEqual(reader.execute("SELECT price_georgia FROM cars WHERE id=7").fetchone(), (None,))
        with mock.patch.object(dbv, "_connect", side_effect=connect), mock.patch.object(dbv, "_read_fresh", side_effect=read):
            proof = dbv.verify_price_roundtrip(self.path, 7)
        self.assertEqual(proof["status"], "PASS")
        self.assertEqual(set(proof["directions"]), {"price_uah", "price_georgia"})
        self.assertEqual(observed, [(20000, None), (20000, 1), (20000, None), (1, None), (20000, None)])
        self.assertEqual(statements.count("COMMIT"), 4)
        self.assertGreaterEqual(len(connections), 9)
        self.assertEqual(reader.execute("SELECT price_georgia FROM cars WHERE id=7").fetchone(), (None,))
        self.assertEqual(self.row(), before)
        self.assertEqual(self.row(1), (1, 1, 50000, 12345, "published"))

    def test_existing_georgia_price_is_restored(self):
        self.keepalive.execute("UPDATE cars SET price_georgia=17000 WHERE id=7")
        self.keepalive.commit()
        before = self.row()
        self.assertEqual(dbv.verify_price_roundtrip(self.path, "7")["status"], "PASS")
        self.assertEqual(self.row(), before)

    def test_crosswrite_in_either_direction_rolls_back_before_commit(self):
        for field, changed in (("price_georgia", "price_uah=price_uah+1"),
                               ("price_uah", "price_georgia=5")):
            with self.subTest(field=field):
                self.trigger(field, changed)
                before = self.row()
                with self.assertRaisesRegex(dbv.VerificationError, "PRECOMMIT_ROW_INVARIANT_FAILED"):
                    dbv.verify_price_roundtrip(self.path, 7)
                self.assertEqual(self.row(), before)
                self.keepalive.execute("DROP TRIGGER crosswrite")
                self.keepalive.commit()

    def test_nonprice_crosswrite_rolls_back(self):
        self.trigger("price_georgia", "model='unexpected'")
        before = self.row()
        with self.assertRaisesRegex(dbv.VerificationError, "PRECOMMIT_ROW_INVARIANT_FAILED"):
            dbv.verify_price_roundtrip(self.path, 7)
        self.assertEqual(self.row(), before)

    def test_trigger_modifying_another_car_is_rolled_back(self):
        for field in ("price_georgia", "price_uah"):
            with self.subTest(field=field):
                self.keepalive.execute("CREATE TRIGGER crossrow AFTER UPDATE OF " + field + " ON cars "
                                       "WHEN NEW.id=7 BEGIN UPDATE cars SET price_uah=999 WHERE id=1; END")
                self.keepalive.commit()
                before, other_before = self.row(), self.row(1)
                with self.assertRaisesRegex(dbv.VerificationError, "PRECOMMIT_CARS_INVARIANT_FAILED"):
                    dbv.verify_price_roundtrip(self.path, 7)
                self.assertEqual(self.row(), before)
                self.assertEqual(self.row(1), other_before)
                self.keepalive.execute("DROP TRIGGER crossrow")
                self.keepalive.commit()

    def test_restore_trigger_cannot_modify_another_car(self):
        self.keepalive.execute("CREATE TRIGGER crossrow_restore AFTER UPDATE OF price_georgia ON cars "
                               "WHEN NEW.id=7 AND NEW.price_georgia IS NULL "
                               "BEGIN UPDATE cars SET model='unexpected' WHERE id=1; END")
        self.keepalive.commit()
        other_before = self.row(1)
        with self.assertRaisesRegex(dbv.VerificationError, "RESTORATION_NEEDED") as caught:
            dbv.verify_price_roundtrip(self.path, 7)
        self.assertEqual(self.row(1), other_before)
        self.assertEqual(self.row(), (7, 0, 20000, 1, "test"))
        self.assertEqual(caught.exception.details["restore_error"], "RESTORATION_CARS_INVARIANT_FAILED")
        self.assertEqual(caught.exception.details["original_prices"]["price_georgia"], None)

    def test_exception_after_commit_restores_with_commit(self):
        before = self.row()
        real_read = dbv._read_fresh
        for failure_call in (2, 4):  # GE and UA committed readbacks.
            with self.subTest(failure_call=failure_call):
                calls = 0

                def read(*args):
                    nonlocal calls
                    calls += 1
                    if calls == failure_call:
                        raise OSError("injected readback failure")
                    return real_read(*args)

                with mock.patch.object(dbv, "_read_fresh", side_effect=read):
                    with self.assertRaisesRegex(dbv.VerificationError, "injected readback failure") as caught:
                        dbv.verify_price_roundtrip(self.path, 7)
                self.assertEqual(self.row(), before)
                receipt = json.loads(pathlib.Path(caught.exception.details["journal_path"]).read_text())
                self.assertEqual(receipt["status"], "FAILED_RESTORED")
                self.assertFalse(receipt["restoration_needed"])

    def test_concurrent_edit_is_preserved_and_durable_conflict_is_reported(self):
        real_read = dbv._read_fresh
        calls = 0

        def read(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                with sqlite3.connect(self.path) as writer:
                    writer.execute("UPDATE cars SET price_georgia=25000, model='owner edit' WHERE id=7")
            return real_read(*args)

        with mock.patch.object(dbv, "_read_fresh", side_effect=read):
            with self.assertRaisesRegex(dbv.VerificationError, "RESTORATION_NEEDED") as caught:
                dbv.verify_price_roundtrip(self.path, 7)
        self.assertEqual(self.row(), (7, 0, 20000, 25000, "owner edit"))
        receipt = json.loads(pathlib.Path(caught.exception.details["journal_path"]).read_text())
        self.assertTrue(receipt["restoration_needed"])
        self.assertEqual(receipt["original_prices"], {"price_uah": 20000, "price_georgia": None})
        self.assertEqual(receipt["restore_error"], "RESTORATION_CONFLICT")
        self.assertEqual(receipt["restore_detail"]["observed_prices"]["price_georgia"], 25000)

    def test_explicit_unpublished_car_required(self):
        before = self.row(1)
        for car_id in (None, "", "  ", True, 1, 999):
            with self.subTest(car_id=car_id), self.assertRaises(dbv.VerificationError):
                dbv.verify_price_roundtrip(self.path, car_id)
        self.assertEqual(self.row(1), before)
        for published in (None, 2, -1):
            self.keepalive.execute("UPDATE cars SET published=? WHERE id=7", (published,))
            self.keepalive.commit()
            with self.assertRaisesRegex(dbv.VerificationError, "EXPLICITLY_UNPUBLISHED"):
                dbv.verify_price_roundtrip(self.path, 7)

    def test_missing_published_column_is_rejected(self):
        path = self.path.parent / "legacy.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE cars(id INTEGER, price_uah INTEGER, price_georgia INTEGER)")
            conn.execute("INSERT INTO cars VALUES(7,20000,NULL)")
        with self.assertRaisesRegex(dbv.VerificationError, "REQUIRED_CAR_COLUMNS_MISSING"):
            dbv.verify_price_roundtrip(path, 7)

    def test_backup_includes_wal_and_never_overwrites(self):
        target = self.path.parent / "backup.db"
        self.assertTrue(pathlib.Path(str(self.path) + "-wal").is_file())
        dbv.backup_sqlite(self.path, target)
        with sqlite3.connect(target) as conn:
            self.assertEqual(conn.execute("SELECT * FROM cars WHERE id=7").fetchone(), self.row())
        original_bytes = target.read_bytes()
        with self.assertRaises(FileExistsError):
            dbv.backup_sqlite(self.path, target)
        self.assertEqual(target.read_bytes(), original_bytes)
        with self.assertRaisesRegex(dbv.VerificationError, "BACKUP_EQUALS_SOURCE"):
            dbv.backup_sqlite(self.path, self.path)


if __name__ == "__main__":
    unittest.main()
