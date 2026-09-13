"""Number lifecycle/concurrency and hash-pinned actual source entrypoints.

Actual source tests use UA_ART_ALLOCATOR_SCHEMA and UA_ART_ALLOCATOR_DB outside
the repository. Only reviewed function/class AST nodes execute, with temporary
SQLite paths; raw CRM module top-level imports and /home/Carix never execute.
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


allocator = load("car_number_allocator", PACKAGE / "runtime/car_number_allocator.py")
integration = load("allocator_integration_test", PACKAGE / "allocator_integration.py")


class AllocatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "crm.db"
        with self.connect() as conn:
            conn.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY AUTOINCREMENT, auto_number TEXT, note TEXT)")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        self.addCleanup(conn.close)
        return conn

    def create(self, note=""):
        with self.connect() as conn:
            number = allocator.reserve(conn)
            conn.execute("INSERT INTO cars(auto_number,note) VALUES(?,?)", (number, note))
        return number

    def test_delete_highest_never_reuses_committed_number(self):
        self.assertEqual([self.create() for _ in range(3)], ["UA-0001", "UA-0002", "UA-0003"])
        with self.connect() as conn:
            conn.execute("DELETE FROM cars WHERE auto_number='UA-0003'")
        self.assertEqual(self.create(), "UA-0004")

    def test_delete_every_card_preserves_sequence(self):
        for _ in range(3):
            self.create()
        with self.connect() as conn:
            conn.execute("DELETE FROM cars")
        self.assertEqual(self.create(), "UA-0004")

    def test_legacy_deletion_before_first_reservation_uses_sqlite_history(self):
        with self.connect() as conn:
            conn.execute("INSERT INTO cars(id,auto_number) VALUES(18,'UA-0018')")
            conn.execute("DELETE FROM cars")
        self.assertEqual(self.create(), "UA-0019")

    def test_out_of_order_suffix_uses_maximum_not_last_insert(self):
        with self.connect() as conn:
            conn.executemany("INSERT INTO cars(auto_number) VALUES(?)", [("UA-0900",), ("UA-0002",)])
        self.assertEqual(self.create(), "UA-0901")

    def test_tombstone_and_media_history_seed_earlier_deleted_custom_ids(self):
        with self.connect() as conn:
            conn.execute("CREATE TABLE ua_spec_lifecycle_archive(auto_number TEXT)")
            conn.execute("INSERT INTO ua_spec_lifecycle_archive VALUES('UA-0300')")
            conn.execute("CREATE TABLE media(auto_number TEXT)")
            conn.execute("INSERT INTO media VALUES('UA-0500')")
        self.assertEqual(self.create(), "UA-0501")

    def test_committed_reservation_without_insert_still_not_reissued(self):
        with self.connect() as conn:
            self.assertEqual(allocator.reserve(conn), "UA-0001")
        self.assertEqual(self.create(), "UA-0002")

    def test_rollback_does_not_create_phantom_card_or_commit_prior_edits(self):
        self.create("before")
        conn = self.connect()
        conn.execute("UPDATE cars SET note='uncommitted'")
        self.assertEqual(allocator.reserve(conn), "UA-0002")
        conn.execute("INSERT INTO cars(auto_number) VALUES('UA-0002')")
        conn.rollback()
        with self.connect() as reader:
            self.assertEqual(reader.execute("SELECT auto_number,note FROM cars").fetchall(), [("UA-0001", "before")])
        self.assertEqual(self.create(), "UA-0002")

    def test_allocation_error_preserves_caller_transaction_and_prior_changes(self):
        self.create("before")
        conn = self.connect()
        conn.execute("UPDATE cars SET note='caller edit'")
        with patch.object(allocator, "_seed", side_effect=RuntimeError("probe failure")):
            with self.assertRaisesRegex(RuntimeError, "probe failure"):
                allocator.reserve(conn)
        self.assertTrue(conn.in_transaction)
        conn.commit()
        self.assertEqual(conn.execute("SELECT note FROM cars").fetchone()[0], "caller edit")
        self.assertEqual(self.create(), "UA-0002")

    def test_failure_without_caller_transaction_rolls_back_own_work(self):
        conn = self.connect()
        with patch.object(allocator, "_seed", side_effect=RuntimeError("probe failure")):
            with self.assertRaisesRegex(RuntimeError, "probe failure"):
                allocator.reserve(conn)
        self.assertFalse(conn.in_transaction)
        self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='ua_card_number_sequence'").fetchone())

    def test_reservation_does_not_commit_before_card_insert(self):
        conn = self.connect()
        self.assertEqual(allocator.reserve(conn), "UA-0001")
        self.assertTrue(conn.in_transaction)
        with self.connect() as reader:
            self.assertIsNone(reader.execute("SELECT name FROM sqlite_master WHERE name='ua_card_number_sequence'").fetchone())
        conn.rollback()

    def test_invalid_prefix_fails_without_transaction(self):
        conn = self.connect()
        for value in ("ua-", "../UA-", "UA-%", "", None):
            with self.assertRaisesRegex(allocator.AllocationError, "PREFIX_INVALID"):
                allocator.reserve(conn, value)
        self.assertFalse(conn.in_transaction)

    def test_invalid_existing_sequence_fails_instead_of_resetting(self):
        conn = self.connect()
        conn.execute("CREATE TABLE ua_card_number_sequence(prefix TEXT PRIMARY KEY,high_water)")
        conn.execute("INSERT INTO ua_card_number_sequence VALUES('UA-','corrupt')")
        conn.commit()
        with self.assertRaisesRegex(allocator.AllocationError, "SEQUENCE_INVALID"):
            allocator.reserve(conn)

    def test_ensure_existing_number_preserves_identity_without_second_reservation(self):
        self.create()
        with self.connect() as conn:
            self.assertEqual(allocator.ensure_card_number(conn, 1), ("UA-0001", False))
            self.assertEqual(conn.execute("SELECT high_water FROM ua_card_number_sequence").fetchone()[0], 1)

    def test_ensure_blank_number_assigns_and_rolls_back_with_caller(self):
        with self.connect() as conn:
            conn.execute("INSERT INTO cars(id,note) VALUES(8,'existing')")
        conn = self.connect()
        conn.execute("UPDATE cars SET note='caller change' WHERE id=8")
        self.assertEqual(allocator.ensure_card_number(conn, 8), ("UA-0009", True))
        conn.rollback()
        self.assertEqual(conn.execute("SELECT auto_number,note FROM cars").fetchone(), (None, "existing"))

    def test_ensure_missing_card_does_not_reserve_or_commit(self):
        conn = self.connect()
        with self.assertRaisesRegex(allocator.AllocationError, "CARD_MISSING"):
            allocator.ensure_card_number(conn, 8)
        self.assertFalse(conn.in_transaction)
        self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='ua_card_number_sequence'").fetchone())

    def test_busy_database_fails_without_guess_or_duplicate_reservation(self):
        owner = self.connect()
        first = allocator.reserve(owner)
        owner.execute("INSERT INTO cars(auto_number) VALUES(?)", (first,))
        contender = sqlite3.connect(self.path, timeout=0.02)
        self.addCleanup(contender.close)
        with self.assertRaises(sqlite3.OperationalError):
            allocator.reserve(contender)
        self.assertFalse(contender.in_transaction)
        owner.commit()
        self.assertEqual(self.create(), "UA-0002")

    def test_stale_read_transaction_fails_preserving_its_caller_state(self):
        with self.connect() as setup:
            setup.execute("PRAGMA journal_mode=WAL")
        self.create()
        reader = self.connect()
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM cars").fetchall()
        self.assertEqual(self.create(), "UA-0002")
        with self.assertRaises(sqlite3.OperationalError):
            allocator.reserve(reader)
        self.assertTrue(reader.in_transaction)
        reader.rollback()
        self.assertEqual(self.create(), "UA-0003")

    def test_concurrent_connections_reserve_and_create_24_distinct_cards(self):
        barrier = threading.Barrier(8)
        def worker(index):
            barrier.wait()
            result = []
            conn = sqlite3.connect(self.path, timeout=10)
            try:
                for _ in range(3):
                    with conn:
                        code = allocator.reserve(conn)
                        conn.execute("INSERT INTO cars(auto_number,note) VALUES(?,?)", (code, str(index)))
                        result.append(code)
                return result
            finally:
                conn.close()
        with ThreadPoolExecutor(max_workers=8) as pool:
            codes = [code for values in pool.map(worker, range(8)) for code in values]
        self.assertEqual(len(set(codes)), 24)
        self.assertEqual(sorted(codes), ["UA-%04d" % n for n in range(1, 25)])

    def test_concurrent_processes_use_same_persisted_sequence(self):
        code = '''import sqlite3,sys
sys.path.insert(0,sys.argv[1])
from car_number_allocator import reserve
conn=sqlite3.connect(sys.argv[2],timeout=10)
try:
 for unused in range(6):
  with conn:
   number=reserve(conn)
   conn.execute("INSERT INTO cars(auto_number) VALUES(?)",(number,))
finally: conn.close()
'''
        processes = [subprocess.Popen([sys.executable, "-c", code, str(PACKAGE / "runtime"), str(self.path)],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(3)]
        for process in processes:
            output, error = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, output + error)
        with self.connect() as conn:
            rows = conn.execute("SELECT auto_number FROM cars ORDER BY auto_number").fetchall()
        self.assertEqual(rows, [("UA-%04d" % n,) for n in range(1, 19)])


@unittest.skipUnless(os.environ.get("UA_ART_ALLOCATOR_SCHEMA") and os.environ.get("UA_ART_ALLOCATOR_DB"),
                     "Actual reviewed source paths required")
class ActualSourceTests(unittest.TestCase):
    # Deliberately do not import either full production module. The relevant
    # database queue/transaction methods execute from their exact AST source.
    def setUp(self):
        AllocatorTests.setUp(self)
        self.schema_source = Path(os.environ["UA_ART_ALLOCATOR_SCHEMA"]).read_text()
        self.db_source = Path(os.environ["UA_ART_ALLOCATOR_DB"]).read_text()
        patcher = patch.dict(sys.modules, {"car_number_allocator": allocator})
        patcher.start()
        self.addCleanup(patcher.stop)

    connect = AllocatorTests.connect

    def schema_function(self, source):
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "next_auto_number")
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<reviewed-schema-function>", "exec"), namespace)
        return namespace["next_auto_number"]

    def database(self, source):
        names = {"_ua_sql_pishet", "_ua_fayl_zahvatit", "_ua_fayl_otpustit", "_UaKursor", "Soedinenie", "connect", "create_card", "get_card", "update_card_field", "set_card_review"}
        nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names)
        namespace = {"sqlite3": sqlite3, "os": os, "BASE_DIR": self.temp.name, "DB_FILE": str(self.path),
                     "ZAMOK": threading.RLock(), "ZAMOK_OZHIDANIE": 2, "_UA_FAYL_SOSTOYANIE": threading.local(),
                     "ST_ON_REVIEW": "on_review", "ST_APPROVED_OWNER": "approved_owner",
                     "now": lambda: "isolated-test-time", "log_action": lambda *args: None}
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in {"CAR_FIELDS", "CLIENT_FIELDS"}:
                    namespace[node.targets[0].id] = ast.literal_eval(node.value)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<reviewed-db-functions>", "exec"), namespace)
        return types.SimpleNamespace(**namespace)

    def ai_store(self, database):
        location = os.environ.get("UA_ART_ALLOCATOR_AI_FILTER")
        if not location:
            self.skipTest("Actual ai_filter source path required")
        candidate = integration.patch_ai_filter(Path(location).read_text())
        names = {"store", "find_by_vin", "_ua_auto10_card_number"}
        nodes = [n for n in ast.parse(candidate).body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names)
        namespace = {"db": database}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<reviewed-ai-filter-functions>", "exec"), namespace)
        return namespace["store"]

    def prepare_ai_database(self):
        with self.connect() as conn:
            for column in ("brand", "model", "year", "vin", "fuel", "color", "review_status", "created_by", "created_at", "approved_by", "updated_at", "published"):
                conn.execute("ALTER TABLE cars ADD COLUMN " + column + " TEXT")
        return self.database(integration.patch_db(self.db_source))

    def test_actual_ai_store_create_delete_create_uses_single_unique_reservation(self):
        database = self.prepare_ai_database()
        store = self.ai_store(database)
        first_id, first_number, first_new = store({"brand": "Kia", "vin": "FIXTURE-A"}, 1)
        self.assertEqual((first_number, first_new), ("UA-0001", True))
        with database.connect() as conn:
            conn.execute("DELETE FROM cars WHERE id=?", (first_id,))
        second_id, second_number, second_new = store({"brand": "Audi", "vin": "FIXTURE-B"}, 1)
        self.assertEqual((second_number, second_new), ("UA-0002", True))
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(store({"model": "A6", "vin": "FIXTURE-B"}, 1), (second_id, "UA-0002", False))
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT high_water FROM ua_card_number_sequence").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT model FROM cars WHERE id=?", (second_id,)).fetchone()[0], "A6")

    def test_actual_ai_store_existing_blank_number_is_atomic_and_only_assigned_once(self):
        database = self.prepare_ai_database()
        store = self.ai_store(database)
        with database.connect() as conn:
            conn.execute("INSERT INTO cars(id,vin,brand) VALUES(8,'FIXTURE-C','Kia')")
        self.assertEqual(store({"vin": "FIXTURE-C"}, 1), (8, "UA-0009", False))
        self.assertEqual(store({"vin": "FIXTURE-C"}, 1), (8, "UA-0009", False))
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT high_water FROM ua_card_number_sequence").fetchone()[0], 9)

    def test_actual_ai_store_concurrent_distinct_vins_keep_unique_stable_numbers(self):
        database = self.prepare_ai_database()
        store = self.ai_store(database)
        barrier = threading.Barrier(6)
        def create(index):
            barrier.wait()
            return store({"vin": "FIXTURE-%s" % index, "brand": "Kia"}, 1)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(create, range(6)))
        self.assertEqual(len({row[0] for row in results}), 6)
        self.assertEqual(sorted(row[1] for row in results), ["UA-%04d" % i for i in range(1, 7)])
        self.assertTrue(all(row[2] for row in results))

    def test_actual_old_allocator_reproduces_deleted_highest_uid_reuse(self):
        old = self.schema_function(self.schema_source)
        with self.connect() as conn:
            conn.executemany("INSERT INTO cars(id,auto_number) VALUES(?,?)", [(17, "UA-0017"), (18, "UA-0018")])
            conn.execute("DELETE FROM cars WHERE id=18")
            self.assertEqual(old(conn), "UA-0018")
            patched = self.schema_function(integration.patch_cars_schema(self.schema_source))
            self.assertEqual(patched(conn), "UA-0019")

    def test_actual_db_create_card_gets_number_in_same_native_transaction(self):
        with self.connect() as conn:
            for column in ("brand", "vin", "review_status", "created_by", "created_at"):
                conn.execute("ALTER TABLE cars ADD COLUMN " + column + " TEXT")
            conn.execute("CREATE TABLE clients(id INTEGER PRIMARY KEY,name TEXT,review_status TEXT,created_by INTEGER,created_at TEXT)")
        database = self.database(integration.patch_db(self.db_source))
        first = database.create_card("cars", {"brand": "Kia", "vin": "fixture", "auto_number": "UA-9999"}, 1)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT auto_number FROM cars WHERE id=?", (first,)).fetchone()[0], "UA-0001")
            conn.execute("DELETE FROM cars WHERE id=?", (first,))
        second = database.create_card("cars", {"brand": "Audi"}, 1)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT auto_number FROM cars WHERE id=?", (second,)).fetchone()[0], "UA-0002")
        client = database.create_card("clients", {"name": "Fixture client"}, 1)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT name FROM clients WHERE id=?", (client,)).fetchone()[0], "Fixture client")
            self.assertEqual(conn.execute("SELECT high_water FROM ua_card_number_sequence WHERE prefix='UA-'").fetchone()[0], 2)

    def test_actual_db_insert_failure_rolls_back_sequence_and_releases_queue(self):
        database = self.database(integration.patch_db(self.db_source))
        with self.assertRaises(sqlite3.OperationalError):
            database.create_card("cars", {"brand": "Kia"}, 1)
        with database.connect() as conn:
            self.assertEqual(allocator.reserve(conn), "UA-0001")
            conn.rollback()

    def test_hash_patcher_refuses_unreviewed_source_and_second_patch(self):
        with self.assertRaisesRegex(integration.IntegrationError, "UNREVIEWED"):
            integration.patch_cars_schema(self.schema_source.replace('n = 0', 'n = 1', 1))
        with self.assertRaisesRegex(integration.IntegrationError, "ALREADY_PATCHED"):
            integration.patch_cars_schema(integration.patch_cars_schema(self.schema_source))
        with self.assertRaisesRegex(integration.IntegrationError, "ALREADY_PATCHED"):
            integration.patch_db(integration.patch_db(self.db_source))


if __name__ == "__main__":
    unittest.main()
