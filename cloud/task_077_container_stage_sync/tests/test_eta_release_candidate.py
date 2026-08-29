"""
test_eta_release_candidate.py — sandbox test suite for TASK 079.

All tests operate exclusively on temporary SQLite databases and temporary
files created within the test process. No production path, real CRM file,
or real PythonAnywhere resource is ever touched.
"""

import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "patcher"))
import eta_release_candidate as rc  # noqa: E402
import live_patcher  # noqa: E402


SCHEMA = """
CREATE TABLE cars (
    id INTEGER PRIMARY KEY,
    vin TEXT,
    price INTEGER,
    description TEXT,
    days_to_kyiv INTEGER,
    eta_manual TEXT,
    status TEXT,
    published INTEGER,
    updated_at TEXT
);
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER,
    field TEXT,
    old_value TEXT,
    new_value TEXT,
    actor TEXT,
    created_at TEXT
);
"""


def make_db(rows):
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    for row in rows:
        conn.execute(
            "INSERT INTO cars(id, vin, price, description, days_to_kyiv, eta_manual, "
            "status, published, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            row,
        )
    conn.commit()
    conn.close()
    return path


def fetch_row(db_path, car_id):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, vin, price, description, days_to_kyiv, eta_manual, status, "
            "published, updated_at FROM cars WHERE id=?",
            (car_id,),
        )
        row = cur.fetchone()
        cols = ["id", "vin", "price", "description", "days_to_kyiv", "eta_manual",
                "status", "published", "updated_at"]
        return dict(zip(cols, row))
    finally:
        conn.close()


class WriteEtaSyncTests(unittest.TestCase):
    def setUp(self):
        self.db_path = make_db([
            (9, "VIN0009", 12000, "Опис авто. 9 вересня 2026 авто прибуде до клієнта.",
             13, "2026-09-28", "ge_to_kyiv", 1, "2026-01-01T00:00:00+00:00"),
            (10, "VIN0010", 13000, "Опис 10.", None, "2026-09-28", "ge_waiting", 0,
             "2026-01-01T00:00:00+00:00"),
            (11, "VIN0011", 14000, "Опис 11.", None, "2026-09-28", "korea_port", 1,
             "2026-01-01T00:00:00+00:00"),
            (12, "VIN0012", 15000, "Опис 12.", 5, "2026-08-01", "korea_port", 0,
             "2026-01-01T00:00:00+00:00"),
        ])

    def tearDown(self):
        os.remove(self.db_path)

    def conn(self):
        return sqlite3.connect(self.db_path)

    def test_n_values_0_1_30_400(self):
        for n in (0, 1, 30, 400):
            c = self.conn()
            result = rc.write_eta_sync(c, 12, n, "tester")
            c.close()
            self.assertEqual(result["postimage"]["days_to_kyiv"], n)
            expected_eta = rc.compute_eta(n)
            self.assertEqual(result["postimage"]["eta_manual"], expected_eta)

    def test_invalid_negative_and_401(self):
        for bad in (-1, 401):
            c = self.conn()
            with self.assertRaises(rc.InvalidInputError):
                rc.write_eta_sync(c, 12, bad, "tester")
            c.close()

    def test_invalid_car_id_types(self):
        c = self.conn()
        with self.assertRaises(rc.InvalidInputError):
            rc.write_eta_sync(c, "12", 30, "tester")
        c.close()

    def test_idempotence(self):
        c = self.conn()
        r1 = rc.write_eta_sync(c, 12, 30, "tester")
        c.close()
        c = self.conn()
        r2 = rc.write_eta_sync(c, 12, 30, "tester")
        c.close()
        self.assertEqual(r1["postimage"]["days_to_kyiv"], r2["postimage"]["days_to_kyiv"])
        self.assertEqual(r1["postimage"]["eta_manual"], r2["postimage"]["eta_manual"])

    def test_protected_status_never_normalized(self):
        c = self.conn()
        result = rc.write_eta_sync(
            c, 10, 30, "tester", normalize_status=True,
            allowed_ferry_statuses=frozenset({"ge_waiting"}),
        )
        c.close()
        self.assertEqual(result["postimage"]["status"], "ge_waiting")

    def test_allowed_ferry_normalization(self):
        c = self.conn()
        result = rc.write_eta_sync(
            c, 11, 30, "tester", normalize_status=True,
            allowed_ferry_statuses=frozenset({"korea_port"}),
        )
        c.close()
        self.assertEqual(result["postimage"]["status"], rc.CANONICAL_FERRY_STATUS)

    def test_published_preimage_preserved_zero(self):
        c = self.conn()
        result = rc.write_eta_sync(c, 10, 30, "tester")
        c.close()
        self.assertEqual(result["postimage"]["published"], 0)

    def test_published_preimage_preserved_one(self):
        c = self.conn()
        result = rc.write_eta_sync(c, 9, 30, "tester")
        c.close()
        self.assertEqual(result["postimage"]["published"], 1)

    def test_unrelated_fields_untouched(self):
        before = fetch_row(self.db_path, 9)
        c = self.conn()
        rc.write_eta_sync(c, 9, 30, "tester")
        c.close()
        after = fetch_row(self.db_path, 9)
        self.assertEqual(before["vin"], after["vin"])
        self.assertEqual(before["price"], after["price"])
        self.assertEqual(before["description"], after["description"])


class ReleaseOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.db_path = make_db([
            (9, "VIN0009", 12000, "Опис авто. 9 вересня 2026 авто прибуде до клієнта.",
             13, "2026-09-28", "ge_to_kyiv", 1, "2026-01-01T00:00:00+00:00"),
            (12, "VIN0012", 15000, "Опис 12.", 5, "2026-08-01", "korea_port", 0,
             "2026-01-01T00:00:00+00:00"),
        ])
        self.tmpdir = tempfile.mkdtemp()
        self.card_path = os.path.join(self.tmpdir, "card.html")
        self.diag_path = os.path.join(self.tmpdir, "diag.html")
        self.video_path = os.path.join(self.tmpdir, "video_catalog.html")
        self.site_path = os.path.join(self.tmpdir, "site_catalog.html")
        with open(self.card_path, "w", encoding="utf-8") as f:
            f.write("OLD CARD")
        with open(self.video_path, "w", encoding="utf-8") as f:
            f.write("OLD VIDEO CATALOG")
        with open(self.site_path, "w", encoding="utf-8") as f:
            f.write("OLD SITE CATALOG")
        # diag_path intentionally does not exist -> exercises placeholder path
        self.file_paths = {
            "card": self.card_path,
            "diag": self.diag_path,
            "video": self.video_path,
            "site": self.site_path,
        }

    def tearDown(self):
        os.remove(self.db_path)

    def build_ok(self, row):
        return {
            "card": ("CARD days=%s eta=%s status=%s" % (
                row["days_to_kyiv"], row["eta_manual"], row["status"])).encode("utf-8"),
            "diag": b"DIAGNOSTIC PLACEHOLDER",
            "video": b"VIDEO CATALOG UPDATED",
            "site": b"SITE CATALOG UPDATED",
        }

    def test_commit_happens_before_publisher_runs(self):
        observed = {}

        def publisher(car_id, row):
            observed["row"] = rc.read_back(self.db_path, car_id)
            return True

        result = rc.run_eta_sync_release(
            self.db_path, 12, 30, "tester", self.file_paths, self.build_ok, publisher,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(observed["row"]["days_to_kyiv"], 30)

    def test_pass_produces_exactly_one_success_message(self):
        result = rc.run_eta_sync_release(
            self.db_path, 12, 30, "tester", self.file_paths, self.build_ok,
            lambda car_id, row: True,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["message"].startswith("SUCCESS"))
        self.assertEqual(result["message"].count("SUCCESS"), 1)

    def test_publisher_failure_rolls_back_db_and_files(self):
        before_row = fetch_row(self.db_path, 12)
        with open(self.card_path, "rb") as f:
            before_card = f.read()

        result = rc.run_eta_sync_release(
            self.db_path, 12, 99, "tester", self.file_paths, self.build_ok,
            lambda car_id, row: False,
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["message"].startswith("FAILURE"))

        after_row = fetch_row(self.db_path, 12)
        self.assertEqual(before_row["days_to_kyiv"], after_row["days_to_kyiv"])
        self.assertEqual(before_row["eta_manual"], after_row["eta_manual"])
        self.assertEqual(before_row["published"], after_row["published"])

        with open(self.card_path, "rb") as f:
            after_card = f.read()
        self.assertEqual(before_card, after_card)
        self.assertFalse(os.path.exists(self.diag_path))

    def test_partial_file_install_rolls_back(self):
        def build_bad(row):
            content = self.build_ok(row)
            # Simulate a partial/broken install target (bad key not in file_paths)
            content["nonexistent_logical_name"] = b"BAD"
            return content

        before_row = fetch_row(self.db_path, 12)
        result = rc.run_eta_sync_release(
            self.db_path, 12, 15, "tester", self.file_paths, build_bad,
            lambda car_id, row: True,
        )
        self.assertEqual(result["status"], "FAIL")
        after_row = fetch_row(self.db_path, 12)
        self.assertEqual(before_row["days_to_kyiv"], after_row["days_to_kyiv"])

    def test_readback_style_failure_rolls_back(self):
        # Force a downstream failure after commit by making build_staged_content raise.
        def build_fail(row):
            raise RuntimeError("simulated delayed overwrite / build failure")

        before_row = fetch_row(self.db_path, 9)
        result = rc.run_eta_sync_release(
            self.db_path, 9, 30, "tester", self.file_paths, build_fail,
            lambda car_id, row: True,
        )
        self.assertEqual(result["status"], "FAIL")
        after_row = fetch_row(self.db_path, 9)
        self.assertEqual(before_row["days_to_kyiv"], after_row["days_to_kyiv"])
        self.assertEqual(before_row["published"], after_row["published"])

    def test_exact_db_row_restoration(self):
        before_row = fetch_row(self.db_path, 9)
        rc.run_eta_sync_release(
            self.db_path, 9, 30, "tester", self.file_paths, self.build_ok,
            lambda car_id, row: False,
        )
        after_row = fetch_row(self.db_path, 9)
        self.assertEqual(before_row, after_row)

    def test_exact_file_byte_restoration(self):
        with open(self.video_path, "rb") as f:
            before_bytes = f.read()
        rc.run_eta_sync_release(
            self.db_path, 9, 30, "tester", self.file_paths, self.build_ok,
            lambda car_id, row: False,
        )
        with open(self.video_path, "rb") as f:
            after_bytes = f.read()
        self.assertEqual(before_bytes, after_bytes)

    def test_ua0009_0010_0011_target_values(self):
        # Independently confirm the required end-state for the sync group.
        c = sqlite3.connect(self.db_path)
        result = rc.write_eta_sync(
            c, 9, 30, "tester", normalize_status=True,
            allowed_ferry_statuses=frozenset(),
        )
        c.close()
        self.assertEqual(result["postimage"]["eta_manual"], "2026-09-28")
        self.assertEqual(result["postimage"]["days_to_kyiv"], 30)

    def test_ua0012_diagnostic_placeholder_created(self):
        result = rc.run_eta_sync_release(
            self.db_path, 12, 30, "tester", self.file_paths, self.build_ok,
            lambda car_id, row: True,
            normalize_status=True, allowed_ferry_statuses=frozenset({"korea_port"}),
        )
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(os.path.exists(self.diag_path))
        with open(self.diag_path, "rb") as f:
            self.assertEqual(f.read(), b"DIAGNOSTIC PLACEHOLDER")
        row = fetch_row(self.db_path, 12)
        self.assertEqual(row["status"], rc.CANONICAL_FERRY_STATUS)
        self.assertEqual(row["days_to_kyiv"], 30)
        self.assertEqual(row["eta_manual"], "2026-09-28")


class SanitizerTests(unittest.TestCase):
    def test_removes_only_stale_arrival_sentence(self):
        text = (
            "Автомобіль пройшов повне сервісне обслуговування 3 травня 2024 року. "
            "9 вересня 2026 авто прибуде до клієнта. "
            "Аукціонна дата продажу була 1 січня 2023 року."
        )
        sanitized, removed = rc.sanitize_stale_arrival_sentence(
            text, must_contain_fragment="9 вересня 2026"
        )
        self.assertEqual(len(removed), 1)
        self.assertIn("9 вересня 2026", removed[0])
        self.assertIn("сервісне обслуговування", sanitized)
        self.assertIn("Аукціонна дата", sanitized)
        self.assertNotIn("9 вересня 2026", sanitized)

    def test_preserves_unrelated_dates_without_arrival_keyword(self):
        text = "Реєстрація закінчується 9 вересня 2026 року."
        sanitized, removed = rc.sanitize_stale_arrival_sentence(
            text, must_contain_fragment="9 вересня 2026"
        )
        self.assertEqual(removed, [])
        self.assertIn("9 вересня 2026", sanitized)

    def test_preserves_arrival_sentence_without_date(self):
        text = "Авто скоро прибуде до клієнта."
        sanitized, removed = rc.sanitize_stale_arrival_sentence(text)
        self.assertEqual(removed, [])
        self.assertIn("прибуде", sanitized)


class AnchorAndFunctionGuardTests(unittest.TestCase):
    def test_verify_anchor_accepts_matching_bytes(self):
        content = b"print('hello')"
        digest = hashlib.sha256(content).hexdigest()
        saved = dict(rc.ANCHOR_SHA256)
        try:
            rc.ANCHOR_SHA256["test_fixture.py"] = digest
            self.assertTrue(rc.verify_anchor("test_fixture.py", content))
        finally:
            rc.ANCHOR_SHA256.clear()
            rc.ANCHOR_SHA256.update(saved)

    def test_verify_anchor_rejects_mismatch(self):
        with self.assertRaises(rc.AnchorMismatchError):
            rc.verify_anchor("db.py", b"definitely not the real live db.py bytes")

    def test_extract_function_sources_rejects_duplicates(self):
        src = "def prinyat():\n    pass\n\ndef prinyat():\n    pass\n"
        with self.assertRaises(rc.ETASyncError):
            rc.extract_function_sources(src, ("prinyat",))

    def test_extract_function_sources_single_definition(self):
        src = "def apply_value():\n    return 1\n"
        found = rc.extract_function_sources(src, ("apply_value",))
        self.assertIn("return 1", found["apply_value"])

    def test_live_patcher_fail_closed_on_arbitrary_local_content(self):
        tmpdir = tempfile.mkdtemp()
        fake_db_py = os.path.join(tmpdir, "db.py")
        with open(fake_db_py, "w", encoding="utf-8") as f:
            f.write("# arbitrary content, not real production bytes\n")
        with self.assertRaises(rc.AnchorMismatchError):
            live_patcher.verify_and_extract({"db.py": fake_db_py})

    def test_live_patcher_apply_always_fail_closed(self):
        tmpdir = tempfile.mkdtemp()
        fake_konteyner = os.path.join(tmpdir, "konteyner.py")
        with open(fake_konteyner, "w", encoding="utf-8") as f:
            f.write("def prinyat():\n    pass\n")
        with self.assertRaises(live_patcher.rc.ETASyncError):
            live_patcher.apply({"konteyner.py": fake_konteyner}, tmpdir)


if __name__ == "__main__":
    unittest.main()
