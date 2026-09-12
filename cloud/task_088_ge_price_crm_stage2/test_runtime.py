#!/usr/bin/env python3
"""SQLite fixture tests only; these do not verify the production DB or bot."""
import json
import pathlib
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest import mock

import runtime as r


class FixtureDB:
    def __init__(self, path):
        self.path = path
        self.connections = 0
        self.statements = []
        self.fail_fresh_connect = False

    def connect(self):
        self.connections += 1
        if self.fail_fresh_connect and self.connections == 2:
            raise sqlite3.OperationalError("fixture read-back connection failure")
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.set_trace_callback(self.statements.append)
        return conn

    @staticmethod
    def now():
        return "fixture-new-time"


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.temp.name) / "fixture.db"
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                CREATE TABLE cars (
                    id INTEGER PRIMARY KEY, price_uah INTEGER, price_georgia INTEGER DEFAULT NULL,
                    price_history TEXT, updated_at TEXT, status INTEGER, vin TEXT, photos TEXT);
                CREATE TABLE audit (
                    actor_id INTEGER, action TEXT, entity_type TEXT, entity_id INTEGER,
                    field TEXT, old_value TEXT, new_value TEXT, created_at TEXT);
                INSERT INTO cars VALUES (1, 12000, 9000, '{"1":11000}', 'old-time', 3, 'VIN1', 'photos1');
                INSERT INTO cars(id,price_uah,price_history,updated_at,status,vin,photos)
                    VALUES (2, 14000, '{"1":13000}', 'old-time', NULL, 'VIN2', 'photos2');
            ''')
        self.db = FixtureDB(self.path)
        self.bindings = mock.patch.multiple(r, create=True, db=self.db,
            price_history=lambda car: json.loads(car["price_history"] or "{}"),
            jdump=lambda value: json.dumps(value, sort_keys=True),
            S=types.SimpleNamespace(stage_of=lambda value: value, num=lambda value: str(value)))
        self.bindings.start()
        self.parser = mock.patch.dict(sys.modules, {"price_parser": None})
        self.parser.start()

    def tearDown(self):
        self.parser.stop()
        self.bindings.stop()
        self.temp.cleanup()

    def rows(self):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT * FROM cars ORDER BY id")]

    def audit(self):
        with sqlite3.connect(self.path) as conn:
            return conn.execute("SELECT field,old_value,new_value FROM audit").fetchall()

    def test_georgia_commits_only_selected_price_and_reads_new_connection(self):
        before = self.rows()
        ok, message = r._task088_apply_selected_price(1, "price_georgia", "11 400 USD", 8)
        self.assertTrue(ok, message)
        expected = [dict(before[0], price_georgia=11400, updated_at="fixture-new-time"), before[1]]
        self.assertEqual(self.rows(), expected)
        self.assertEqual(self.audit(), [("price_georgia", "9000", "11400")])
        self.assertEqual(self.db.connections, 2)
        self.assertIn("11400", message)
        updates = [query for query in self.db.statements if query.startswith("UPDATE cars")]
        self.assertTrue(updates)
        self.assertTrue(all("SET price_georgia=" in query and "price_uah=" not in query for query in updates))

    def test_ukraine_preserves_georgia_and_existing_history(self):
        before = self.rows()
        ok, message = r._task088_apply_selected_price(1, "price_uah", "12 700", 8)
        self.assertTrue(ok, message)
        expected = dict(before[0], price_uah=12700, updated_at="fixture-new-time",
                        price_history=json.dumps({"1":11000, "3":12700}, sort_keys=True))
        self.assertEqual(self.rows(), [expected, before[1]])
        self.assertEqual(self.audit(), [("price_uah", "12000", "12700")])

    def test_default_null_georgia_survives_ukraine_edit_and_blank_ge_input(self):
        ok, message = r._task088_apply_selected_price(2, "price_uah", "14500", 8)
        self.assertTrue(ok, message)
        self.assertIsNone(self.rows()[1]["price_georgia"])
        self.assertEqual(json.loads(self.rows()[1]["price_history"]), {"1":14500})
        before = self.rows()
        ok, _ = r._task088_apply_selected_price(2, "price_georgia", "", 8)
        self.assertFalse(ok)
        self.assertEqual(self.rows(), before)
        ok, message = r._task088_apply_selected_price(2, "price_georgia", "10500", 8)
        self.assertTrue(ok, message)
        self.assertEqual(self.rows()[1]["price_uah"], 14500)
        self.assertEqual(self.audit()[-1], ("price_georgia", None, "10500"))

    def test_invalid_input_and_nonallowlisted_fields_never_open_db(self):
        before = self.rows()
        for value in (None, "", "0", "-1", "abc", "11.5", "100 EUR", True, str(2**63)):
            with self.subTest(value=value):
                self.assertFalse(r._task088_apply_selected_price(1, "price_georgia", value, 8)[0])
        for field in ("price", "price_uah = 1", "cost_purchase", None):
            with self.subTest(field=field):
                self.assertFalse(r._task088_apply_selected_price(1, field, "10000", 8)[0])
        self.assertEqual(self.db.connections, 0)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.audit(), [])

    def test_shared_parser_default_ua_target_cannot_redirect_georgia_write(self):
        calls = []
        def parse(text, **kwargs):
            calls.append((text, kwargs))
            return types.SimpleNamespace(ok=True, value=10800, field="price_uah")
        with mock.patch.dict(sys.modules, {"price_parser": types.SimpleNamespace(parse_sale_price_message=parse)}):
            ok, message = r._task088_apply_selected_price(1, "price_georgia", "10800", 8)
        self.assertTrue(ok, message)
        self.assertEqual(self.rows()[0]["price_uah"], 12000)
        self.assertEqual(self.rows()[0]["price_georgia"], 10800)
        self.assertEqual(calls[0][1], {"in_price_uah_wait": True})

    def test_parser_dependency_and_runtime_errors_fail_before_db_access(self):
        before = self.rows()
        for error in (ImportError("fixture dependency"), RuntimeError("fixture parser failure")):
            with self.subTest(error=type(error).__name__):
                parse = mock.Mock(side_effect=error)
                with mock.patch.dict(sys.modules, {"price_parser": types.SimpleNamespace(parse_sale_price_message=parse)}):
                    ok, message = r._task088_apply_selected_price(1, "price_georgia", "11000", 8)
                self.assertFalse(ok)
                self.assertIn("не записана", message)
                self.assertNotIn(str(error), message)
        self.assertEqual(self.db.connections, 0)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.audit(), [])

    def test_missing_row_never_creates_a_car_or_audit_record(self):
        before = self.rows()
        ok, _ = r._task088_apply_selected_price(99, "price_georgia", "11000", 8)
        self.assertFalse(ok)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.audit(), [])

    def test_cross_write_triggers_rollback_in_both_directions(self):
        before = self.rows()
        for selected, other in (("price_uah", "price_georgia"), ("price_georgia", "price_uah")):
            with self.subTest(selected=selected):
                with sqlite3.connect(self.path) as conn:
                    conn.execute("CREATE TRIGGER corrupt AFTER UPDATE OF " + selected +
                                 " ON cars BEGIN UPDATE cars SET " + other + "=1 WHERE id=NEW.id; END")
                ok, _ = r._task088_apply_selected_price(1, selected, "11000", 8)
                self.assertFalse(ok)
                self.assertEqual(self.rows(), before)
                self.assertEqual(self.audit(), [])
                with sqlite3.connect(self.path) as conn:
                    conn.execute("DROP TRIGGER corrupt")

    def test_audit_trigger_and_other_car_mutations_are_rolled_back(self):
        before = self.rows()
        triggers = (
            "CREATE TRIGGER corrupt AFTER UPDATE OF price_georgia ON cars BEGIN UPDATE cars SET vin='changed' WHERE id=2; END",
            "CREATE TRIGGER corrupt AFTER INSERT ON audit BEGIN UPDATE cars SET price_uah=1 WHERE id=1; END",
            "CREATE TRIGGER corrupt AFTER INSERT ON audit BEGIN UPDATE cars SET photos='changed' WHERE id=2; END")
        for sql in triggers:
            with self.subTest(trigger=triggers.index(sql)):
                with sqlite3.connect(self.path) as conn:
                    conn.execute(sql)
                self.assertFalse(r._task088_apply_selected_price(1, "price_georgia", "11000", 8)[0])
                self.assertEqual(self.rows(), before)
                self.assertEqual(self.audit(), [])
                with sqlite3.connect(self.path) as conn:
                    conn.execute("DROP TRIGGER corrupt")

    def test_audit_failure_rolls_back_price_and_history(self):
        before = self.rows()
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE audit")
        self.assertFalse(r._task088_apply_selected_price(1, "price_uah", "13000", 8)[0])
        self.assertEqual(self.rows(), before)

    def test_fresh_readback_connection_failure_cannot_claim_success(self):
        self.db.fail_fresh_connect = True
        ok, message = r._task088_apply_selected_price(1, "price_georgia", "11000", 8)
        self.assertFalse(ok)
        self.assertIn("не подтверждена", message)
        # The commit already happened. Do not silently overwrite it on read-back
        # failure; this result explicitly requires checking the saved value.
        self.assertEqual(self.rows()[0]["price_georgia"], 11000)
        self.assertEqual(self.rows()[0]["price_uah"], 12000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
