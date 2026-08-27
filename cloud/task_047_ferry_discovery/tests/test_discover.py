import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discover  # noqa: E402
import transform  # noqa: E402


class TestSecretRedaction(unittest.TestCase):
    def test_scan_detects_secret(self):
        self.assertTrue(transform.scan_for_secrets('{"token": "abcdef123"}'))

    def test_scan_ignores_safe_fields(self):
        self.assertFalse(transform.scan_for_secrets('{"status": "ok", "sha256": "aabbcc"}'))


class TestDiscoveryInventory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_html_occurrence_inventory_chip(self):
        path = self._write("card.html", '<div class="chip">В море · Корея → Грузия</div>')
        report = discover.discover_registry([path])
        self.assertEqual(len(report["occurrences"]), 1)
        occ = report["occurrences"][0]
        self.assertEqual(occ["form"], "chip")
        self.assertEqual(occ["classification"], "TARGET")
        self.assertIn("sha256", report["files"][0])

    def test_html_occurrence_inventory_etap_tut(self):
        path = self._write(
            "card2.html",
            '<div class="etap tut"><div class="krug">2</div>Море: Корея → Грузия</div>',
        )
        report = discover.discover_registry([path])
        forms = [o["form"] for o in report["occurrences"]]
        self.assertIn("etap_tut", forms)

    def test_python_legacy_alias_literal_preserved(self):
        py_src = 'LEGACY_ROUTE_ALIAS = {"old": "Море"}\n'
        path = self._write("aliases.py", py_src)
        report = discover.discover_registry([path])
        occs = [o for o in report["occurrences"] if o["form"] == "python_literal"]
        self.assertEqual(len(occs), 1)
        self.assertEqual(occs[0]["classification"], "LEGACY_INPUT_ALIAS")
        self.assertEqual(occs[0]["action"], "PRESERVE")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), py_src)

    def test_python_user_facing_literal(self):
        py_src = 'ROUTE_LABEL_TEXT = "Море: Корея -> Грузия"\n'
        path = self._write("labels.py", py_src)
        report = discover.discover_registry([path])
        occs = [o for o in report["occurrences"] if o["form"] == "python_literal"]
        self.assertEqual(occs[0]["classification"], "USER_FACING")

    def test_python_ambiguous_literal(self):
        py_src = 'SOME_VALUE = "Море"\n'
        path = self._write("misc.py", py_src)
        report = discover.discover_registry([path])
        occs = [o for o in report["occurrences"] if o["form"] == "python_literal"]
        self.assertEqual(occs[0]["classification"], "AMBIGUOUS")

    def test_missing_file_reported(self):
        report = discover.discover_registry([os.path.join(self.tmp.name, "does_not_exist.html")])
        self.assertEqual(report["files"][0]["status"], "MISSING")


class TestOverallBlocked(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_blocked_on_ambiguous(self):
        path = os.path.join(self.tmp.name, "card.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Черное Море является ориентиром")
        report = discover.run_discovery([path], [])
        self.assertEqual(report["overall"], "BLOCKED")
        self.assertGreater(report["ambiguous_count"], 0)

    def test_missing_optional_file_reported_but_visible(self):
        report = discover.run_discovery([os.path.join(self.tmp.name, "missing.html")], [])
        self.assertEqual(report["files"][0]["status"], "MISSING")

    def test_ok_when_only_target_occurrences(self):
        path = os.path.join(self.tmp.name, "card.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<div class="chip">В море · Корея → Грузия</div>')
        report = discover.run_discovery([path], [])
        self.assertEqual(report["overall"], "OK")


def _make_crm_db(path, table="cards", id_col="id", extra_table=None, dup_id=None):
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE {table} ({id_col} TEXT, status TEXT, route TEXT)")
    for i in range(1, 10):
        conn.execute(f"INSERT INTO {table} VALUES (?, ?, ?)", (f"UA-{i:04d}", "active", "Korea-Georgia"))
    if dup_id:
        conn.execute(f"INSERT INTO {table} VALUES (?, ?, ?)", (dup_id, "active", "Korea-Georgia"))
    if extra_table:
        conn.execute(f"CREATE TABLE {extra_table} ({id_col} TEXT)")
    conn.commit()
    conn.close()


class TestCRM(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "crm.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ok_single_row(self):
        _make_crm_db(self.db_path)
        result = discover.read_crm_verified(self.db_path, ["UA-0001"])
        self.assertEqual(result["status"], "OK")
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["sha256_before"], result["sha256_after"])

    def test_blocked_missing_db(self):
        result = discover.read_crm_verified(os.path.join(self.tmp.name, "nope.sqlite3"), ["UA-0001"])
        self.assertEqual(result["status"], "MISSING")

    def test_blocked_multiple_tables(self):
        _make_crm_db(self.db_path, extra_table="orders")
        result = discover.read_crm_verified(self.db_path, ["UA-0001"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("table_ambiguous", result["reason"])

    def test_blocked_multiple_id_columns(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE cards (id TEXT, card_id TEXT, status TEXT)")
        conn.execute("INSERT INTO cards VALUES ('UA-0001', 'UA-0001', 'active')")
        conn.commit()
        conn.close()
        result = discover.read_crm_verified(self.db_path, ["UA-0001"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("id_column_ambiguous", result["reason"])

    def test_blocked_duplicate_row(self):
        _make_crm_db(self.db_path, dup_id="UA-0001")
        result = discover.read_crm_verified(self.db_path, ["UA-0001"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("duplicate_row", result["reason"])

    def test_blocked_missing_row(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE cards (id TEXT, status TEXT)")
        conn.commit()
        conn.close()
        result = discover.read_crm_verified(self.db_path, ["UA-0001"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("missing_row", result["reason"])

    def test_blocked_not_allowlisted_id(self):
        _make_crm_db(self.db_path)
        result = discover.read_crm_verified(self.db_path, ["UA-9999"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_blocked_corrupted_db_quick_check(self):
        with open(self.db_path, "wb") as f:
            f.write(b"not a real sqlite database at all, just garbage bytes")
        result = discover.read_crm_verified(self.db_path, ["UA-0001"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_run_discovery_blocked_when_crm_blocked(self):
        _make_crm_db(self.db_path, extra_table="orders")
        report = discover.run_discovery([], [], crm_db_path=self.db_path, crm_ids=["UA-0001"])
        self.assertEqual(report["overall"], "BLOCKED")


class TestReceiptSecretScan(unittest.TestCase):
    def test_run_discovery_receipt_has_no_secrets(self):
        report = discover.run_discovery([], [])
        self.assertFalse(transform.scan_for_secrets(report["_serialized_receipt"]))


if __name__ == "__main__":
    unittest.main()
